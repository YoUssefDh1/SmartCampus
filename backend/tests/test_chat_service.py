from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AIUnavailableError
from app.main import app
from app.services import chat_service
from app.services.rag_service import RetrievedChunk


client = TestClient(app, raise_server_exceptions=False)


def test_chat_creates_session_and_carries_history(monkeypatch):
    calls = []

    async def fake_generate_reply(messages):
        calls.append(messages)
        return f"Réponse {len(calls)}"

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)

    first = client.post("/api/v1/chat/message", json={"message": "Bonjour"})
    assert first.status_code == 200
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
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == first_body["session_id"]
    assert calls[1][-3:] == [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Réponse 1"},
        {"role": "user", "content": "Je veux étudier l'informatique"},
    ]


def test_chat_rejects_blank_messages():
    response = client.post("/api/v1/chat/message", json={"message": "   "})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_chat_returns_service_unavailable_error(monkeypatch):
    async def unavailable(_messages):
        raise AIUnavailableError("Ollama indisponible.")

    monkeypatch.setattr(chat_service, "generate_reply", unavailable)
    response = client.post("/api/v1/chat/message", json={"message": "Bonjour"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_UNAVAILABLE"


def test_chat_requests_french_rephrase_for_unrecognized_language(monkeypatch):
    calls = []

    async def fake_generate_reply(messages):
        calls.append(messages)
        return "Pouvez-vous reformuler votre question en français ?"

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)
    response = client.post("/api/v1/chat/message", json={"message": "asdf qwerty"})

    assert response.status_code == 200
    assert response.json()["language"] == "unknown"
    assert "ask them to rephrase in French" in calls[-1][0]["content"]


def test_chat_history_is_bounded(monkeypatch):
    calls = []

    async def fake_generate_reply(messages):
        calls.append(messages)
        return "D'accord."

    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)
    session_id = "bounded-history-test"
    for index in range(8):
        response = client.post(
            "/api/v1/chat/message",
            json={"session_id": session_id, "message": f"Question numero {index}"},
        )
        assert response.status_code == 200

    assert len(calls[-1]) == 1 + chat_service.MAX_HISTORY_MESSAGES + 1
    assert calls[-1][1]["content"] == "Question numero 1"


def test_chat_uses_retrieved_context_and_returns_source(monkeypatch):
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
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sources"] == [{
        "source_id": "source-1",
        "title": "Guide officiel",
        "origin": "guide.pdf",
        "page": 3,
    }]
    assert "<excerpt>Conditions vérifiées.</excerpt>" in calls[0][0]["content"]


def test_chat_does_not_claim_official_facts_without_retrieved_sources(monkeypatch):
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
    )

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert "No relevant official-document excerpts were found" in calls[0][0]["content"]
