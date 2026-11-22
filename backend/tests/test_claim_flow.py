"""Tests SA-29 : rattachement d'une session visiteur à un compte candidat (claim pattern)."""
import uuid

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.core.security import create_guest_access_token
from app.db.session import get_dict_connection
from app.main import app
from app.models.user import Role
from app.services import chat_service
from tests.conftest import TEST_PASSWORD, requires_db

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch):
    """Ollama ne tourne pas pendant les tests : la réponse de l'assistant est figée."""
    async def fake_generate_reply(messages):
        return "Je note votre intérêt."

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)


def _chat(guest, message: str) -> dict:
    response = client.post("/api/v1/chat/message", headers=guest.headers, json={"message": message})
    assert response.status_code == 200, response.text
    return response.json()


def _claim(candidate, guest_session_id: str, guest_token: str, confirm_transfer: bool = True):
    return client.post("/api/v1/auth/claim", headers=candidate["headers"], json={
        "guest_session_id": guest_session_id, "guest_token": guest_token,
        "confirm_transfer": confirm_transfer,
    })


def _login_headers(email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- Transfert réussi ---

@requires_db
def test_claim_transfers_the_conversation_and_merges_the_draft(guest, candidate):
    _chat(guest, "Bonjour, je cherche une licence en informatique à l'IIT")

    response = _claim(candidate, guest.session_id, guest.token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "success"
    assert body["user_id"] == candidate["id"]
    assert len(body["claimed_conversation_ids"]) == 1
    assert body["transferred_messages_count"] == 2  # le message du visiteur + la réponse
    assert body["merged_profile_draft"]["interests"] == ["Informatique"]
    assert body["merged_profile_draft"]["current_level"] == "Licence"
    assert body["merged_profile_draft"]["preferred_language"] == "fr"

    with get_dict_connection() as connection:
        conversation = connection.execute(
            "SELECT candidate_id, guest_session_id, profile_draft FROM conversation WHERE id = %s",
            (body["claimed_conversation_ids"][0],),
        ).fetchone()
        session = connection.execute(
            "SELECT claimed_at, claimed_by_user_id FROM guest_session WHERE id = %s",
            (guest.session_id,),
        ).fetchone()

    assert str(conversation["candidate_id"]) == candidate["id"]
    assert conversation["guest_session_id"] is None
    assert conversation["profile_draft"]["target_institutions"] == ["IIT"]  # aucune colonne dédiée
    assert session["claimed_at"] is not None
    assert str(session["claimed_by_user_id"]) == candidate["id"]


@requires_db
def test_claim_never_overwrites_an_official_profile_value(guest, candidate):
    with get_dict_connection() as connection:
        connection.execute(
            "UPDATE candidate_profile SET current_level = 'Master', interests = %s WHERE user_id = %s",
            (Jsonb(["Gestion"]), candidate["id"]),
        )
    _chat(guest, "Je veux une licence en informatique")

    merged = _claim(candidate, guest.session_id, guest.token).json()["merged_profile_draft"]

    assert merged["current_level"] == "Master"
    assert merged["interests"] == ["Gestion"]


@requires_db
def test_claim_of_a_session_without_conversation_still_converts_it(guest, candidate):
    response = _claim(candidate, guest.session_id, guest.token)

    assert response.status_code == 200, response.text
    assert response.json()["claimed_conversation_ids"] == []
    assert response.json()["transferred_messages_count"] == 0


# --- Isolation : le visiteur perd l'accès aux données transférées ---

@requires_db
def test_claimed_conversation_leaves_the_guest_history(guest, candidate):
    conversation_id = _chat(guest, "Bonjour")["session_id"]

    assert _claim(candidate, guest.session_id, guest.token).status_code == 200

    sessions = client.get("/api/v1/chat/sessions", headers=guest.headers)
    history = client.get(f"/api/v1/chat/sessions/{conversation_id}/history", headers=guest.headers)
    assert sessions.status_code == 200
    assert sessions.json() == {"items": [], "total": 0}
    assert history.status_code == 403


# --- Double preuve d'identité et de possession ---

@requires_db
def test_claim_requires_a_candidate_token(guest):
    response = client.post("/api/v1/auth/claim", json={
        "guest_session_id": guest.session_id, "guest_token": guest.token,
        "confirm_transfer": True})

    assert response.status_code == 401


@requires_db
def test_claim_is_refused_to_a_manager(guest, make_account):
    manager = make_account(Role.IIT_MANAGER.value, "iit")

    response = client.post("/api/v1/auth/claim", headers=_login_headers(manager.email), json={
        "guest_session_id": guest.session_id, "guest_token": guest.token,
        "confirm_transfer": True})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


@requires_db
def test_claim_rejects_the_token_of_another_guest(guest, other_guest, candidate):
    response = _claim(candidate, guest.session_id, other_guest.token)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_GUEST_TOKEN"


@requires_db
def test_claim_rejects_a_tampered_guest_token(guest, candidate):
    response = _claim(candidate, guest.session_id, guest.token[:-4] + "abcd")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_GUEST_TOKEN"


@requires_db
def test_claim_rejects_an_explicit_refusal(guest, candidate):
    response = _claim(candidate, guest.session_id, guest.token, confirm_transfer=False)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# --- Intégrité de la session invitée ---

@requires_db
def test_claim_of_an_unknown_session_is_a_404(candidate):
    unknown_id = str(uuid.uuid4())
    # Jeton signé pour une session qui n'a jamais été créée en base.
    response = _claim(candidate, unknown_id, create_guest_access_token(unknown_id))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GUEST_SESSION_NOT_FOUND"


@requires_db
def test_claim_of_an_expired_session_is_a_400(guest, candidate):
    with get_dict_connection() as connection:
        connection.execute(
            """
            UPDATE guest_session
            SET created_at = now() - interval '2 hours', expires_at = now() - interval '1 hour'
            WHERE id = %s
            """,
            (guest.session_id,),
        )

    response = _claim(candidate, guest.session_id, guest.token)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "GUEST_SESSION_EXPIRED"


@requires_db
def test_claiming_twice_is_a_conflict(guest, candidate):
    assert _claim(candidate, guest.session_id, guest.token).status_code == 200

    replay = _claim(candidate, guest.session_id, guest.token)

    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "GUEST_SESSION_ALREADY_CLAIMED"


@requires_db
def test_a_session_cannot_be_claimed_by_a_second_candidate(guest, candidate, make_account):
    assert _claim(candidate, guest.session_id, guest.token).status_code == 200
    other = make_account(Role.CANDIDATE.value)

    replay = client.post("/api/v1/auth/claim", headers=_login_headers(other.email), json={
        "guest_session_id": guest.session_id, "guest_token": guest.token,
        "confirm_transfer": True})

    assert replay.status_code == 409
    with get_dict_connection() as connection:
        session = connection.execute("SELECT claimed_by_user_id FROM guest_session WHERE id = %s",
                                     (guest.session_id,)).fetchone()
    assert str(session["claimed_by_user_id"]) == candidate["id"]
