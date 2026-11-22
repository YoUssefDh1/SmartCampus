from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AIUnavailableError
from app.main import app
from app.services import chat_service
from app.services.rag_service import RetrievedChunk
from tests.conftest import GuestContext, requires_db


client = TestClient(app, raise_server_exceptions=False)


@requires_db
def test_chat_creates_session_and_carries_history(guest: GuestContext, monkeypatch):
    calls = []

    async def fake_generate_reply(messages):
        calls.append(messages)
        return f"Réponse {len(calls)}"

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)

    first = client.post("/api/v1/chat/message", json={"message": "Bonjour"}, headers=guest.headers)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["reply"] == "Réponse 1"
    assert first_body["session_id"]
    assert first_body["sources"] == []
    assert calls[0][0]["role"] == "system"
    assert "Do not invent official IIT/ISB" in calls[0][0]["content"]
    assert first_body["language"] == "fr"

    second = client.post(
        "/api/v1/chat/message",
        json={"session_id": first_body["session_id"], "message": "Je veux étudier l'informatique"},
        headers=guest.headers,
    )
    assert second.status_code == 200, second.text
    assert second.json()["session_id"] == first_body["session_id"]
    assert calls[1][-3:] == [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Réponse 1"},
        {"role": "user", "content": "Je veux étudier l'informatique"},
    ]


@requires_db
def test_chat_requires_guest_token():
    response = client.post("/api/v1/chat/message", json={"message": "Bonjour"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@requires_db
def test_chat_rejects_blank_messages(guest: GuestContext):
    response = client.post("/api/v1/chat/message", json={"message": "   "}, headers=guest.headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@requires_db
def test_chat_returns_service_unavailable_error(guest: GuestContext, monkeypatch):
    async def unavailable(_messages):
        raise AIUnavailableError("Ollama indisponible.")

    monkeypatch.setattr(chat_service, "generate_reply", unavailable)
    response = client.post("/api/v1/chat/message", json={"message": "Bonjour"}, headers=guest.headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_UNAVAILABLE"


@requires_db
def test_chat_requests_french_rephrase_for_unrecognized_language(guest: GuestContext, monkeypatch):
    calls = []

    async def fake_generate_reply(messages):
        calls.append(messages)
        return "Pouvez-vous reformuler votre question en français ?"

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)
    response = client.post("/api/v1/chat/message", json={"message": "asdf qwerty"},
                           headers=guest.headers)

    assert response.status_code == 200, response.text
    assert response.json()["language"] == "unknown"
    assert "ask them to rephrase in French" in calls[-1][0]["content"]


@requires_db
def test_chat_extracts_profile_draft(guest: GuestContext, monkeypatch):
    async def fake_generate_reply(_messages):
        return "Très bon choix."

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)

    response = client.post(
        "/api/v1/chat/message",
        json={"message": "Bonjour, je prépare mon bac et je vise l'informatique à l'IIT"},
        headers=guest.headers,
    )
    assert response.status_code == 200, response.text
    profile = response.json()["profile_updates"]
    assert profile["detected_language"] == "fr"
    assert profile["education_level"] == "Baccalauréat"
    assert "Informatique" in profile["interests"]
    assert "IIT" in profile["target_institutions"]


@requires_db
def test_chat_uses_retrieved_context_and_returns_source(guest: GuestContext, monkeypatch):
    calls = []

    async def fake_retrieve(query, *, settings):
        assert query == "Quelles sont les conditions ?"
        assert settings.rag_enabled
        return [
            RetrievedChunk(
                source_id="source-1",
                title="Guide officiel",
                origin="guide.pdf",
                page=3,
                content="Conditions vérifiées.",
                similarity=0.82,
            )
        ]

    async def fake_generate_reply(messages):
        calls.append(messages)
        return "Selon le guide [1], voici les informations."

    monkeypatch.setattr(chat_service, "get_settings", lambda: Settings(rag_enabled=True))
    monkeypatch.setattr(chat_service, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)
    response = client.post(
        "/api/v1/chat/message",
        json={"message": "Quelles sont les conditions ?"},
        headers=guest.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sources"] == [{
        "source_id": "source-1",
        "title": "Guide officiel",
        "origin": "guide.pdf",
        "page": 3,
    }]
    assert "<excerpt>Conditions vérifiées.</excerpt>" in calls[0][0]["content"]


@requires_db
def test_chat_does_not_claim_official_facts_without_retrieved_sources(guest: GuestContext, monkeypatch):
    calls = []

    async def no_sources(_query, *, settings):
        assert settings.rag_enabled
        return []

    async def fake_generate_reply(messages):
        calls.append(messages)
        return "Je n'ai pas trouvé de source officielle pour confirmer cette information."

    monkeypatch.setattr(chat_service, "get_settings", lambda: Settings(rag_enabled=True))
    monkeypatch.setattr(chat_service, "retrieve", no_sources)
    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)
    response = client.post(
        "/api/v1/chat/message",
        json={"message": "Quelle est la date d'admission ?"},
        headers=guest.headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["sources"] == []
    assert "No relevant official-document excerpts were found" in calls[0][0]["content"]
