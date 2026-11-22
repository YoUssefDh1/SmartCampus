"""Tests SA-25 : sessions visiteur anonymes (création, TTL, quotas, purge)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.errors import ForbiddenError, TooManyRequestsError, UnauthorizedError
from app.core.security import create_guest_access_token, decode_token, get_current_guest_session
from app.db.session import get_connection, get_dict_connection
from app.main import app
from app.services.guest_service import (check_guest_message_allowed,
                                        purge_expired_guest_conversations)
from tests.conftest import requires_db

client = TestClient(app, raise_server_exceptions=False)
settings = get_settings()


def _cleanup(connection, session_id) -> None:
    connection.execute("DELETE FROM conversation WHERE guest_session_id = %s", (session_id,))
    connection.execute("DELETE FROM guest_session WHERE id = %s", (session_id,))


def _insert_guest_session(connection, *, expires_in: timedelta,
                          claimed_at: datetime | None = None) -> str:
    session_id = str(uuid.uuid4())
    # CHECK (expires_at > created_at) : on antidate created_at pour les sessions expirées.
    connection.execute(
        """
        INSERT INTO guest_session (id, created_at, expires_at, claimed_at)
        VALUES (%s, least(now(), now() + %s - interval '1 hour'), now() + %s, %s)
        """,
        (session_id, expires_in, expires_in, claimed_at),
    )
    return session_id


def _insert_user_messages(connection, session_id: str, count: int,
                          created_at_offset: timedelta | None = None) -> None:
    conversation_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO conversation (id, guest_session_id) VALUES (%s, %s)",
        (conversation_id, session_id),
    )
    for _ in range(count):
        if created_at_offset is None:
            connection.execute(
                "INSERT INTO message (conversation_id, role, content) VALUES (%s, 'user', 'bonjour')",
                (conversation_id,),
            )
        else:
            connection.execute(
                """
                INSERT INTO message (conversation_id, role, content, created_at)
                VALUES (%s, 'user', 'bonjour', now() + %s)
                """,
                (conversation_id, created_at_offset),
            )


# --- JWT visiteur (sans base de données) ---

def test_guest_jwt_roundtrip():
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.guest_session_ttl_hours)
    token = create_guest_access_token(session_id, expires_at)

    payload = decode_token(token)
    assert payload.sub == f"guest_{session_id}"
    assert payload.session_id == session_id
    assert payload.role == "guest"


def test_guest_jwt_tampered_is_rejected():
    token = create_guest_access_token(str(uuid.uuid4()))
    with pytest.raises(UnauthorizedError):
        decode_token(token[:-4] + "abcd")


# --- POST /api/v1/auth/guest ---

@requires_db
def test_create_guest_session_endpoint():
    r = client.post("/api/v1/auth/guest")
    assert r.status_code == 201
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["role"] == "guest"
    assert data["session_id"]
    assert data["expires_at"]

    payload = decode_token(data["access_token"])
    assert payload.session_id == data["session_id"]
    assert payload.role == "guest"

    with get_connection() as connection:
        _cleanup(connection, data["session_id"])


# --- Dépendance get_current_guest_session (contrôle inline du TTL) ---

@app.get("/_test/guest-session")
def _guest_session_route(session=Depends(get_current_guest_session)):
    return {"session_id": session.id}


@requires_db
def test_guest_dependency_accepts_valid_token():
    with get_connection() as connection:
        session_id = _insert_guest_session(connection, expires_in=timedelta(hours=1))
    try:
        token = create_guest_access_token(session_id)
        r = client.get("/_test/guest-session", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["session_id"] == session_id
    finally:
        with get_connection() as connection:
            _cleanup(connection, session_id)


@requires_db
def test_guest_dependency_rejects_expired_token():
    with get_connection() as connection:
        session_id = _insert_guest_session(connection, expires_in=timedelta(hours=1))
        connection.execute(
            """
            UPDATE guest_session
            SET created_at = now() - interval '2 hours', expires_at = now() - interval '1 hour'
            WHERE id = %s
            """,
            (session_id,),
        )
    try:
        token = create_guest_access_token(session_id)
        r = client.get("/_test/guest-session", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        with get_connection() as connection:
            _cleanup(connection, session_id)


@requires_db
def test_guest_dependency_missing_or_unknown_or_not_guest():
    r = client.get("/_test/guest-session")
    assert r.status_code == 401

    unknown_token = create_guest_access_token(str(uuid.uuid4()))
    r = client.get("/_test/guest-session", headers={"Authorization": f"Bearer {unknown_token}"})
    assert r.status_code == 401

    import jwt as pyjwt
    forged = pyjwt.encode(
        {"sub": "user_1", "session_id": str(uuid.uuid4()), "role": "candidate",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    r = client.get("/_test/guest-session", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


# --- Quotas et débit (429) ---

@requires_db
def test_guest_message_quota_exceeded():
    with get_connection() as connection:
        session_id = _insert_guest_session(connection, expires_in=timedelta(hours=1))
        _insert_user_messages(connection, session_id, settings.guest_max_messages,
                              created_at_offset=timedelta(minutes=-5))
    try:
        with get_dict_connection() as connection, pytest.raises(TooManyRequestsError) as exc_info:
            check_guest_message_allowed(connection, session_id)
        assert "Quota de messages invité dépassé" in exc_info.value.message
    finally:
        with get_connection() as connection:
            _cleanup(connection, session_id)


@requires_db
def test_guest_rate_limit_per_minute():
    with get_connection() as connection:
        session_id = _insert_guest_session(connection, expires_in=timedelta(hours=1))
        _insert_user_messages(connection, session_id, settings.guest_rate_limit_per_minute)
    try:
        with get_dict_connection() as connection, pytest.raises(TooManyRequestsError) as exc_info:
            check_guest_message_allowed(connection, session_id)
        assert "Débit de messages invité dépassé" in exc_info.value.message
    finally:
        with get_connection() as connection:
            _cleanup(connection, session_id)


@requires_db
def test_guest_under_quotas_is_allowed():
    with get_dict_connection() as connection:
        session_id = _insert_guest_session(connection, expires_in=timedelta(hours=1))
        _insert_user_messages(connection, session_id, 1)
        check_guest_message_allowed(connection, session_id)  # ne doit pas lever
        _cleanup(connection, session_id)


# --- Purge des conversations expirées ---

@requires_db
def test_purge_deletes_only_expired_unclaimed_conversations():
    with get_connection() as connection:
        expired_id = _insert_guest_session(connection, expires_in=timedelta(hours=-2))
        active_id = _insert_guest_session(connection, expires_in=timedelta(hours=2))
        claimed_id = _insert_guest_session(connection, expires_in=timedelta(hours=-2),
                                           claimed_at=datetime.now(timezone.utc))
        for session_id in (expired_id, active_id, claimed_id):
            _insert_user_messages(connection, session_id, 1)

        deleted = purge_expired_guest_conversations(connection)
        assert deleted >= 1

        def _conversation_count(session_id: str) -> int:
            return connection.execute(
                "SELECT count(*) FROM conversation WHERE guest_session_id = %s", (session_id,)
            ).fetchone()[0]

        assert _conversation_count(expired_id) == 0
        assert _conversation_count(active_id) == 1
        assert _conversation_count(claimed_id) == 1

        # Les lignes guest_session sont conservées (funnel d'inscription).
        assert connection.execute(
            "SELECT count(*) FROM guest_session WHERE id = %s", (expired_id,)
        ).fetchone()[0] == 1

        for session_id in (expired_id, active_id, claimed_id):
            _cleanup(connection, session_id)
