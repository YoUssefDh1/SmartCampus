"""Fixtures partagées : accès base, sessions visiteur et comptes jetables."""
import uuid
from dataclasses import dataclass
from typing import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.db.session import get_connection, get_dict_connection
from app.main import app
from app.models.user import UserAccount
from app.services import user_service

TEST_PASSWORD = "SecurePassword123!"


def database_available() -> bool:
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not database_available(),
                                 reason="PostgreSQL inaccessible (docker compose up db)")


@dataclass
class GuestContext:
    token: str
    session_id: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def make_guest() -> Iterator[Callable[[], GuestContext]]:
    """Fabrique de sessions visiteur réelles (POST /auth/guest), nettoyées en fin de test."""
    client = TestClient(app, raise_server_exceptions=False)
    created: list[str] = []

    def _make() -> GuestContext:
        response = client.post("/api/v1/auth/guest")
        assert response.status_code == 201, response.text
        body = response.json()
        created.append(body["session_id"])
        return GuestContext(token=body["access_token"], session_id=body["session_id"])

    yield _make

    # Ordre imposé : conversation.guest_session_id est ON DELETE SET NULL, or la table
    # exige un propriétaire (CHECK), donc les conversations doivent partir avant la session.
    with get_connection() as connection:
        for session_id in created:
            connection.execute("DELETE FROM conversation WHERE guest_session_id = %s", (session_id,))
            connection.execute("DELETE FROM guest_session WHERE id = %s", (session_id,))


@pytest.fixture
def guest(make_guest) -> GuestContext:
    return make_guest()


@pytest.fixture
def other_guest(make_guest) -> GuestContext:
    """Seconde session visiteur, pour les tests d'isolation."""
    return make_guest()


def random_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


@pytest.fixture
def make_account() -> Iterator[Callable[..., UserAccount]]:
    """Fabrique de comptes (tous rôles), supprimés en fin de test.

    L'inscription publique ne crée que des candidats : les comptes staff passent
    directement par user_service.create_account. La cascade PostgreSQL nettoie
    candidate_profile, refresh_token et les conversations rattachées.
    """
    created: list[str] = []

    def _make(role: str, institution_code: str | None = None, email: str | None = None,
              password: str = TEST_PASSWORD) -> UserAccount:
        with get_dict_connection() as connection:
            account = user_service.create_account(
                connection, email=email or random_email(), password_hash=hash_password(password),
                first_name="Staff", last_name=role.title(), role=role,
                institution_code=institution_code,
            )
        created.append(account.id)
        return account

    yield _make

    with get_dict_connection() as connection:
        for account_id in created:
            connection.execute("DELETE FROM app_user WHERE id = %s", (account_id,))


@pytest.fixture
def candidate() -> Iterator[dict]:
    """Compte candidat inscrit et connecté via l'API : {id, email, token, headers}."""
    client = TestClient(app, raise_server_exceptions=False)
    email = random_email()
    registered = client.post("/api/v1/auth/register", json={
        "email": email, "password": TEST_PASSWORD, "full_name": "John Doe"})
    assert registered.status_code == 201, registered.text

    logged = client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert logged.status_code == 200, logged.text
    token = logged.json()["access_token"]

    account = {"id": registered.json()["id"], "email": email, "token": token,
               "headers": {"Authorization": f"Bearer {token}"}}
    yield account

    with get_dict_connection() as connection:
        connection.execute("DELETE FROM app_user WHERE id = %s", (account["id"],))
