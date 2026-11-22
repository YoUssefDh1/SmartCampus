"""Tests SA-26 : mémoire temporaire (fenêtre glissante, profile_draft, isolation)."""
import uuid

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_dict_connection
from app.main import app
from app.services import chat_service, memory_service
from tests.conftest import GuestContext, requires_db

client = TestClient(app, raise_server_exceptions=False)
settings = get_settings()


def _conversation_id(guest: GuestContext) -> str:
    with get_dict_connection() as connection:
        return str(memory_service.get_or_create_conversation(connection, guest.session_id)["id"])


def _seed_messages(guest: GuestContext, count: int) -> str:
    with get_dict_connection() as connection:
        conversation_id = str(
            memory_service.get_or_create_conversation(connection, guest.session_id)["id"]
        )
        for index in range(count):
            memory_service.save_message(connection, conversation_id, "user", f"Message {index + 1}")
        return conversation_id


# --- Persistance et fenêtre glissante ---

@requires_db
def test_save_and_retrieve_messages(guest: GuestContext):
    conversation_id = _conversation_id(guest)
    with get_dict_connection() as connection:
        memory_service.save_message(connection, conversation_id, "user", "Bonjour", language="fr")
        memory_service.save_message(connection, conversation_id, "assistant", "Bienvenue !")
        messages, profile_draft = memory_service.get_recent_context(connection, conversation_id)

    assert [message["content"] for message in messages] == ["Bonjour", "Bienvenue !"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert profile_draft == {}


@requires_db
def test_conversation_is_reused_and_last_message_at_updated(guest: GuestContext):
    with get_dict_connection() as connection:
        first = memory_service.get_or_create_conversation(connection, guest.session_id)
        assert first["last_message_at"] is None

        memory_service.save_message(connection, str(first["id"]), "user", "Bonjour", language="fr")
        second = memory_service.get_or_create_conversation(connection, guest.session_id)

        assert str(second["id"]) == str(first["id"])
        assert second["last_message_at"] is not None
        assert second["language"] == "fr"


@requires_db
def test_foreign_conversation_id_is_ignored(guest: GuestContext, other_guest: GuestContext):
    foreign_id = _conversation_id(other_guest)
    own_id = _conversation_id(guest)

    with get_dict_connection() as connection:
        resolved = memory_service.get_or_create_conversation(connection, guest.session_id, foreign_id)

    assert str(resolved["id"]) == own_id


@requires_db
def test_sliding_window_is_bounded(guest: GuestContext):
    conversation_id = _seed_messages(guest, settings.memory_window_size + 5)

    with get_dict_connection() as connection:
        messages, _ = memory_service.get_recent_context(connection, conversation_id)

    assert len(messages) == settings.memory_window_size
    assert messages[0]["content"] == "Message 6"
    assert messages[-1]["content"] == f"Message {settings.memory_window_size + 5}"


@requires_db
def test_message_content_is_truncated(guest: GuestContext):
    conversation_id = _conversation_id(guest)
    oversized = "x" * (settings.max_message_length + 500)
    with get_dict_connection() as connection:
        saved = memory_service.save_message(connection, conversation_id, "user", oversized)

    assert len(saved["content"]) == settings.max_message_length


# --- profile_draft : fusion incrémentale ---

def test_merge_profile_draft_keeps_consolidated_keys():
    merged = memory_service.merge_profile_draft(
        {"detected_language": "fr", "interests": ["Informatique"], "target_institutions": ["IIT"]},
        {"detected_language": None, "interests": ["Génie Civil"], "target_institutions": ["IIT", "ISB"]},
    )
    assert merged["detected_language"] == "fr"
    assert merged["interests"] == ["Informatique", "Génie Civil"]
    assert merged["target_institutions"] == ["IIT", "ISB"]


@requires_db
def test_profile_draft_is_updated_incrementally(guest: GuestContext):
    conversation_id = _conversation_id(guest)
    with get_dict_connection() as connection:
        memory_service.update_profile_draft(connection, conversation_id, {
            "detected_language": "fr", "interests": ["Informatique"],
        })
        profile = memory_service.update_profile_draft(connection, conversation_id, {
            "target_institutions": ["IIT"], "interests": ["Gestion"],
        })
        reloaded = memory_service.get_conversation(connection, conversation_id)

    assert profile["detected_language"] == "fr"
    assert set(profile["interests"]) == {"Informatique", "Gestion"}
    assert profile["target_institutions"] == ["IIT"]
    assert reloaded["profile_draft"] == profile


# --- Isolation inter-sessions (ownership porté par le JWT guest) ---

@requires_db
def test_history_is_restricted_to_own_guest_session(guest: GuestContext,
                                                    other_guest: GuestContext, monkeypatch):
    async def fake_generate_reply(_messages):
        return "Bonjour !"

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)
    sent = client.post("/api/v1/chat/message", json={"message": "Bonjour"}, headers=guest.headers)
    assert sent.status_code == 200, sent.text
    conversation_id = sent.json()["session_id"]

    own = client.get(f"/api/v1/chat/sessions/{conversation_id}/history", headers=guest.headers)
    assert own.status_code == 200, own.text
    body = own.json()
    assert body["total_messages"] == 2
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]
    assert body["profile_draft"]["detected_language"] == "fr"

    forbidden = client.get(f"/api/v1/chat/sessions/{conversation_id}/history",
                           headers=other_guest.headers)
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    anonymous = client.get(f"/api/v1/chat/sessions/{conversation_id}/history")
    assert anonymous.status_code == 401


@requires_db
def test_history_of_unknown_conversation_is_not_found(guest: GuestContext):
    response = client.get(f"/api/v1/chat/sessions/{uuid.uuid4()}/history", headers=guest.headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@requires_db
def test_sessions_list_only_own_conversations(guest: GuestContext, other_guest: GuestContext):
    conversation_id = _seed_messages(guest, 1)
    _seed_messages(other_guest, 3)

    listed = client.get("/api/v1/chat/sessions", headers=guest.headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == conversation_id
