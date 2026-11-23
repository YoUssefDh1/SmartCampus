"""Cycle de vie des sessions visiteur anonymes (SA-25) et leur rattachement (SA-29).

Une session est une ligne dans `guest_session` (schema.sql) : pas de colonne `status`,
l'expiration se déduit de `expires_at` et le rattachement d'un compte de `claimed_at`.
Les lignes ne sont jamais supprimées (le funnel d'inscription en dépend) ; la purge
supprime uniquement les conversations des sessions expirées non rattachées.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.core.errors import (AppError, ConflictError, ForbiddenError, NotFoundError,
                             TooManyRequestsError)
from app.db.session import get_connection, get_dict_connection
from app.services.memory_service import merge_profile_draft


@dataclass
class GuestSession:
    id: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    claimed_at: datetime | None = None

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


def _row_to_session(row: dict) -> GuestSession:
    return GuestSession(
        id=str(row["id"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        last_seen_at=row["last_seen_at"],
        claimed_at=row["claimed_at"],
    )


_SESSION_COLUMNS = "id, created_at, expires_at, last_seen_at, claimed_at"


def create_guest_session(connection: psycopg.Connection) -> GuestSession:
    settings = get_settings()
    row = connection.execute(
        f"""
        INSERT INTO guest_session (expires_at)
        VALUES (now() + make_interval(hours => %s))
        RETURNING {_SESSION_COLUMNS}
        """,
        (settings.guest_session_ttl_hours,),
    ).fetchone()
    return _row_to_session(row)


def fetch_guest_session(connection: psycopg.Connection, session_id: str) -> GuestSession | None:
    row = connection.execute(
        f"SELECT {_SESSION_COLUMNS} FROM guest_session WHERE id = %s",
        (session_id,),
    ).fetchone()
    return _row_to_session(row) if row else None


def touch_guest_session(connection: psycopg.Connection, session_id: str) -> None:
    connection.execute(
        "UPDATE guest_session SET last_seen_at = now() WHERE id = %s",
        (session_id,),
    )


def count_user_messages(connection: psycopg.Connection, session_id: str,
                        since: datetime | None = None) -> int:
    """Messages « user » des conversations rattachées à la session visiteur.

    Attend une connexion en `dict_row` (voir app.db.session.get_dict_connection).
    """
    sql = """
        SELECT count(*) AS total
        FROM message m
        JOIN conversation c ON c.id = m.conversation_id
        WHERE c.guest_session_id = %s AND m.role = 'user'
    """
    params: list = [session_id]
    if since is not None:
        sql += " AND m.created_at >= %s"
        params.append(since)
    return connection.execute(sql, params).fetchone()["total"]


def check_guest_message_allowed(connection: psycopg.Connection, session_id: str) -> None:
    """Contrôle quota total + débit par minute avant d'accepter un message visiteur."""
    settings = get_settings()

    since = datetime.now(timezone.utc) - timedelta(minutes=1)
    recent = count_user_messages(connection, session_id, since=since)
    if recent >= settings.guest_rate_limit_per_minute:
        raise TooManyRequestsError(
            f"Débit de messages invité dépassé (limite : {settings.guest_rate_limit_per_minute} "
            "messages par minute). Veuillez ralentir."
        )

    total = count_user_messages(connection, session_id)
    if total >= settings.guest_max_messages:
        raise TooManyRequestsError(
            f"Quota de messages invité dépassé (limite : {settings.guest_max_messages} messages). "
            "Veuillez créer un compte pour continuer."
        )


def purge_expired_guest_conversations(connection: psycopg.Connection | None = None) -> int:
    """Supprime les conversations des sessions expirées jamais converties en compte.

    Les lignes `guest_session` sont conservées : les statistiques du funnel
    (schema.sql) comptent les visiteurs et les conversions via `claimed_at`.
    """
    own_connection = connection is None
    if own_connection:
        connection = get_dict_connection()
    try:
        deleted = connection.execute(
            """
            DELETE FROM conversation
            WHERE guest_session_id IN (
                SELECT id FROM guest_session
                WHERE expires_at < now() AND claimed_at IS NULL
            )
            """
        ).rowcount
        connection.commit()
        return deleted
    finally:
        if own_connection:
            connection.close()


# --- Rattachement d'une session visiteur à un compte candidat (SA-29) ---

CHAT_LANGUAGES = ("fr", "tn", "tn-arabizi")  # valeurs du domaine SQL chat_language


@dataclass
class ClaimResult:
    conversation_ids: list[str] = field(default_factory=list)
    transferred_messages: int = 0
    merged_profile: dict = field(default_factory=dict)


def _merge_candidate_profile(connection: psycopg.Connection, candidate_id: str,
                             draft: dict) -> dict | None:
    """Fusion non destructive du `profile_draft` visiteur dans `candidate_profile`.

    Une valeur officielle déjà renseignée n'est jamais écrasée. `target_institutions`
    n'a pas de colonne dédiée : il reste dans conversation.profile_draft, conservé tel quel.
    """
    language = draft.get("detected_language")
    row = connection.execute(
        """
        UPDATE candidate_profile
        SET interests = CASE WHEN jsonb_array_length(interests) = 0 THEN %s::jsonb
                             ELSE interests END,
            current_level = COALESCE(NULLIF(current_level, ''), %s),
            preferred_language = COALESCE(preferred_language, %s)
        WHERE user_id = %s
        RETURNING interests, current_level, preferred_language
        """,
        (Jsonb(draft.get("interests") or []), draft.get("education_level"),
         language if language in CHAT_LANGUAGES else None, candidate_id),
    ).fetchone()
    return dict(row) if row else None


def claim_guest_session(connection: psycopg.Connection, *, guest_session_id: str,
                        candidate_id: str) -> ClaimResult:
    """Transfère les conversations d'une session visiteur vers un compte candidat.

    Tout se joue dans une transaction, la ligne `guest_session` étant verrouillée
    (FOR UPDATE) : un double clic ou un rejeu simultané ne peut pas doubler le transfert.
    """
    with connection.transaction():
        session = connection.execute(
            "SELECT id, expires_at, claimed_at FROM guest_session WHERE id = %s FOR UPDATE",
            (guest_session_id,),
        ).fetchone()
        if session is None:
            raise NotFoundError("Session invitée introuvable.", code="GUEST_SESSION_NOT_FOUND")
        if session["claimed_at"] is not None:
            raise ConflictError("Cette session invitée a déjà été rattachée à un compte.",
                                code="GUEST_SESSION_ALREADY_CLAIMED")
        if session["expires_at"] <= datetime.now(timezone.utc):
            raise AppError("La session invitée est expirée.", code="GUEST_SESSION_EXPIRED")

        conversations = connection.execute(
            """
            UPDATE conversation
            SET candidate_id = %s, guest_session_id = NULL
            WHERE guest_session_id = %s
            RETURNING id, profile_draft
            """,
            (candidate_id, guest_session_id),
        ).fetchall()

        draft: dict = {}
        for conversation in conversations:
            draft = merge_profile_draft(draft, conversation["profile_draft"] or {})

        profile = _merge_candidate_profile(connection, candidate_id, draft)
        if profile is None:
            raise ForbiddenError("Seul un compte candidat peut rattacher une session visiteur.",
                                 code="NOT_A_CANDIDATE")

        transferred = 0
        if conversations:
            ids = [str(conversation["id"]) for conversation in conversations]
            transferred = connection.execute(
                "SELECT count(*) AS total FROM message WHERE conversation_id = ANY(%s::uuid[])",
                (ids,),
            ).fetchone()["total"]

        connection.execute(
            "UPDATE guest_session SET claimed_at = now(), claimed_by_user_id = %s WHERE id = %s",
            (candidate_id, guest_session_id),
        )

    return ClaimResult(conversation_ids=[str(row["id"]) for row in conversations],
                       transferred_messages=transferred, merged_profile=profile)
