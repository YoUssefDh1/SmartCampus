"""Accès SQL aux comptes (`app_user`), profils candidat et jetons de renouvellement.

Attend des connexions en `dict_row` (voir app.db.session.get_dict_connection).
Aucune décision métier ici : l'inscription, la connexion et la rotation des jetons
sont orchestrées par app.services.auth_service.
"""
import psycopg

from app.core.errors import NotFoundError
from app.models.user import ACCOUNT_ROLES, MANAGER_SCOPE, Role, UserAccount, row_to_account

_USER_COLUMNS = """
    u.id, u.email, u.first_name, u.last_name, u.role, u.is_active, u.created_at,
    i.code AS institution_code
"""
_USER_FROM = "FROM app_user u LEFT JOIN institution i ON i.id = u.institution_id"


def fetch_user_by_id(connection: psycopg.Connection, user_id: str) -> UserAccount | None:
    row = connection.execute(
        f"SELECT {_USER_COLUMNS} {_USER_FROM} WHERE u.id = %s", (user_id,)
    ).fetchone()
    return row_to_account(row) if row else None


def email_exists(connection: psycopg.Connection, email: str) -> bool:
    """L'unicité porte sur `lower(email)` (index app_user_email_key)."""
    return connection.execute(
        "SELECT 1 FROM app_user WHERE lower(email) = lower(%s)", (email,)
    ).fetchone() is not None


def fetch_credentials(connection: psycopg.Connection, email: str) -> tuple[UserAccount, str] | None:
    """Compte + empreinte du mot de passe. L'empreinte ne sort jamais de cette fonction."""
    row = connection.execute(
        f"SELECT {_USER_COLUMNS}, u.password_hash {_USER_FROM} WHERE lower(u.email) = lower(%s)",
        (email,),
    ).fetchone()
    return (row_to_account(row), row["password_hash"]) if row else None


def fetch_institution_id(connection: psycopg.Connection, code: str) -> str | None:
    row = connection.execute(
        "SELECT id FROM institution WHERE code = upper(%s)", (code,)
    ).fetchone()
    return str(row["id"]) if row else None


def create_account(connection: psycopg.Connection, *, email: str, password_hash: str,
                   first_name: str, last_name: str, role: str,
                   institution_code: str | None = None) -> UserAccount:
    """Crée un compte. Pour un candidat, le trigger `trg_app_user_candidate_profile`
    crée la ligne `candidate_profile` sur laquelle pointent toutes les tables candidat.
    """
    if role not in ACCOUNT_ROLES:
        raise ValueError(f"Rôle inconnu : {role!r}")

    expected_scope = MANAGER_SCOPE.get(role)
    if expected_scope:
        if (institution_code or "").upper() != expected_scope:
            raise ValueError(f"Le rôle {role} exige l'établissement {expected_scope}.")
    elif role == Role.CANDIDATE.value:
        institution_code = None  # CHECK app_user_institution_scope

    institution_id = None
    if institution_code:
        institution_id = fetch_institution_id(connection, institution_code)
        if institution_id is None:
            raise NotFoundError(f"Établissement introuvable : {institution_code}.")

    row = connection.execute(
        """
        INSERT INTO app_user (email, first_name, last_name, role, institution_id, password_hash)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, email, first_name, last_name, role, is_active, created_at
        """,
        (email, first_name, last_name, role, institution_id, password_hash),
    ).fetchone()

    return row_to_account({**row, "institution_code": institution_code})


def mark_login(connection: psycopg.Connection, user_id: str) -> None:
    connection.execute("UPDATE app_user SET last_login_at = now() WHERE id = %s", (user_id,))


def store_refresh_token(connection: psycopg.Connection, *, user_id: str, token_hash: str,
                        expires_at) -> str:
    return str(connection.execute(
        """
        INSERT INTO refresh_token (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s) RETURNING id
        """,
        (user_id, token_hash, expires_at),
    ).fetchone()["id"])


def fetch_refresh_token(connection: psycopg.Connection, token_hash: str) -> dict | None:
    return connection.execute(
        "SELECT id, user_id, expires_at, revoked_at FROM refresh_token WHERE token_hash = %s",
        (token_hash,),
    ).fetchone()


def revoke_refresh_token(connection: psycopg.Connection, token_id: str,
                         replaced_by_id: str | None = None) -> None:
    connection.execute(
        "UPDATE refresh_token SET revoked_at = now(), replaced_by_id = %s WHERE id = %s",
        (replaced_by_id, token_id),
    )
