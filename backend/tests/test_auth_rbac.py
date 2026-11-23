"""Tests SA-28 : inscription, connexion, rotation des jetons, RBAC et périmètre école."""
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.errors import ForbiddenError
from app.core.security import (check_resource_ownership, check_school_scope, require_roles)
from app.db.session import get_dict_connection
from app.main import app
from app.models.user import Role, UserAccount
from tests.conftest import TEST_PASSWORD, random_email, requires_db

client = TestClient(app, raise_server_exceptions=False)


# --- Route de test pour le RBAC (même procédé que test_guest_sessions.py) ---

@app.get("/_test/staff-only")
def _staff_only_route(user: UserAccount = Depends(require_roles(Role.IIT_MANAGER, Role.DIRECTION))):
    return {"role": user.role, "school_scope": user.school_scope}


def _register(email: str | None = None, full_name: str = "John Doe",
              password: str = TEST_PASSWORD):
    return client.post("/api/v1/auth/register", json={
        "email": email or random_email(), "password": password, "full_name": full_name,
    })


def _login(email: str, password: str = TEST_PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Inscription ---

@requires_db
def test_register_creates_candidate_and_profile():
    email = random_email()
    response = _register(email=email, full_name="John Doe")

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == email
    assert body["full_name"] == "John Doe"
    assert body["role"] == "candidate"
    assert body["school_scope"] is None
    assert body["is_active"] is True
    assert body["created_at"]

    with get_dict_connection() as connection:
        profile = connection.execute(
            "SELECT 1 FROM candidate_profile WHERE user_id = %s", (body["id"],)
        ).fetchone()
        connection.execute("DELETE FROM app_user WHERE id = %s", (body["id"],))
    assert profile is not None


@requires_db
def test_register_stores_an_argon2_hash_never_the_password():
    response = _register()
    with get_dict_connection() as connection:
        row = connection.execute("SELECT password_hash FROM app_user WHERE id = %s",
                                 (response.json()["id"],)).fetchone()
        connection.execute("DELETE FROM app_user WHERE id = %s", (response.json()["id"],))

    assert row["password_hash"].startswith("$argon2id$")
    assert TEST_PASSWORD not in row["password_hash"]


@requires_db
def test_register_duplicate_email_conflicts_regardless_of_case():
    email = random_email()
    first = _register(email=email)
    assert first.status_code == 201

    second = client.post("/api/v1/auth/register", json={
        "email": email.upper(), "password": TEST_PASSWORD, "full_name": "John Doe"})
    try:
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"
    finally:
        with get_dict_connection() as connection:
            connection.execute("DELETE FROM app_user WHERE id = %s", (first.json()["id"],))


@pytest.mark.parametrize("payload,field", [
    ({"email": "not-an-email", "password": TEST_PASSWORD, "full_name": "John Doe"}, "email"),
    ({"email": "john@example.com", "password": "short", "full_name": "John Doe"}, "password"),
    ({"email": "john@example.com", "password": TEST_PASSWORD, "full_name": "John"}, "full_name"),
])
def test_register_rejects_invalid_payload(payload, field):
    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in [detail["field"] for detail in error["details"]]


# --- Connexion ---

@requires_db
def test_login_returns_tokens_and_user(candidate):
    response = _login(candidate["email"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["access_token"] and body["refresh_token"]
    assert body["user"]["id"] == candidate["id"]
    assert body["user"]["role"] == "candidate"


@requires_db
def test_login_rejects_wrong_password_and_unknown_email(candidate):
    wrong = _login(candidate["email"], "WrongPassword123!")
    unknown = _login(random_email())

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert unknown.json()["error"]["code"] == "INVALID_CREDENTIALS"


@requires_db
def test_login_rejects_disabled_account(candidate):
    with get_dict_connection() as connection:
        connection.execute("UPDATE app_user SET is_active = false WHERE id = %s", (candidate["id"],))

    response = _login(candidate["email"])

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


# --- Renouvellement (rotation) ---

@requires_db
def test_refresh_rotates_and_revokes_the_previous_token(candidate):
    issued = _login(candidate["email"]).json()

    first = client.post("/api/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]})
    assert first.status_code == 200, first.text
    rotated = first.json()
    assert rotated["refresh_token"] != issued["refresh_token"]
    assert rotated["access_token"]

    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]})
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"

    with get_dict_connection() as connection:
        stored = connection.execute(
            "SELECT revoked_at, replaced_by_id FROM refresh_token "
            "WHERE user_id = %s AND replaced_by_id IS NOT NULL", (candidate["id"],)).fetchall()
    assert len(stored) == 1
    assert stored[0]["revoked_at"] is not None
    assert stored[0]["replaced_by_id"] is not None


@requires_db
def test_refresh_rejects_an_unknown_token():
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "inconnu"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


@requires_db
def test_refreshed_access_token_authenticates_me(candidate):
    rotated = client.post("/api/v1/auth/refresh",
                          json={"refresh_token": _login(candidate["email"]).json()["refresh_token"]})

    response = client.get("/api/v1/auth/me", headers=_auth(rotated.json()["access_token"]))

    assert response.status_code == 200
    assert response.json()["id"] == candidate["id"]


# --- GET /me ---

@requires_db
def test_me_returns_the_connected_account(candidate):
    token = _login(candidate["email"]).json()["access_token"]

    response = client.get("/api/v1/auth/me", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == candidate["email"]
    assert body["full_name"] == "John Doe"
    assert body["role"] == "candidate"


def test_me_requires_a_token():
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@requires_db
def test_me_rejects_a_guest_token(guest):
    response = client.get("/api/v1/auth/me", headers=guest.headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@requires_db
def test_me_rejects_a_disabled_account(candidate):
    token = _login(candidate["email"]).json()["access_token"]
    with get_dict_connection() as connection:
        connection.execute("UPDATE app_user SET is_active = false WHERE id = %s", (candidate["id"],))

    response = client.get("/api/v1/auth/me", headers=_auth(token))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"


# --- RBAC : require_roles ---

@requires_db
def test_require_roles_allows_listed_roles(make_account):
    manager = make_account(Role.IIT_MANAGER.value, "iit")
    token = _login(manager.email).json()["access_token"]

    response = client.get("/_test/staff-only", headers=_auth(token))

    assert response.status_code == 200
    assert response.json() == {"role": "iit_manager", "school_scope": "iit"}


@requires_db
def test_require_roles_denies_other_roles(make_account):
    interviewer = make_account(Role.INTERVIEWER.value)
    token = _login(interviewer.email).json()["access_token"]

    response = client.get("/_test/staff-only", headers=_auth(token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@requires_db
def test_require_roles_lets_admin_through(make_account):
    admin = make_account(Role.ADMIN.value)
    token = _login(admin.email).json()["access_token"]

    response = client.get("/_test/staff-only", headers=_auth(token))

    assert response.status_code == 200


@requires_db
def test_require_roles_rejects_guest_tokens(guest):
    response = client.get("/_test/staff-only", headers=guest.headers)

    assert response.status_code == 403


# --- Périmètre : propriété de la ressource et école ---

@requires_db
def test_resource_ownership_allows_owner_and_admin(make_account):
    owner = make_account(Role.CANDIDATE.value)
    admin = make_account(Role.ADMIN.value)

    assert check_resource_ownership(owner.id, owner) is True
    assert check_resource_ownership(owner.id, admin) is True


@requires_db
def test_resource_ownership_denies_another_candidate(make_account):
    owner = make_account(Role.CANDIDATE.value)
    stranger = make_account(Role.CANDIDATE.value)

    with pytest.raises(ForbiddenError) as exc_info:
        check_resource_ownership(owner.id, stranger)
    assert exc_info.value.code == "RESOURCE_ACCESS_DENIED"


@requires_db
def test_school_scope_isolates_iit_from_isb(make_account):
    iit_manager = make_account(Role.IIT_MANAGER.value, "iit")
    isb_manager = make_account(Role.ISB_MANAGER.value, "isb")
    admin = make_account(Role.ADMIN.value)

    assert check_school_scope(iit_manager, "IIT") is True
    assert check_school_scope(admin, "ISB") is True
    with pytest.raises(ForbiddenError):
        check_school_scope(iit_manager, "ISB")
    with pytest.raises(ForbiddenError):
        check_school_scope(isb_manager, "iit")
