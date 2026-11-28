import asyncio
from contextlib import nullcontext

from app.core.config import Settings
from app.schemas.chat import ChatRequest
from app.services import chat_service
from app.services.rag_service import RetrievedChunk


def _configure_chat(monkeypatch, history):
    retrieval_queries = []
    model_calls = []

    async def fake_retrieve(query, *, settings):
        retrieval_queries.append(query)
        return [
            RetrievedChunk(
                source_id="source-1",
                title="Plan d'études - Génie Informatique",
                origin="iit-genie-informatique-curriculum.md",
                page=None,
                content="GLID, SDIA et ARSI.",
                similarity=0.82,
            )
        ]

    async def fake_generate_reply(messages):
        model_calls.append(messages)
        return "Réponse test."

    monkeypatch.setattr(chat_service, "get_settings", lambda: Settings(rag_enabled=True))
    monkeypatch.setattr(chat_service, "get_dict_connection", lambda: nullcontext(object()))
    monkeypatch.setattr(chat_service, "check_guest_message_allowed", lambda *_args: None)
    monkeypatch.setattr(
        chat_service.memory_service,
        "get_or_create_conversation",
        lambda *_args: {"id": "conversation-id"},
    )
    monkeypatch.setattr(chat_service.memory_service, "save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        chat_service.memory_service,
        "update_profile_draft",
        lambda *_args: {},
    )
    monkeypatch.setattr(
        chat_service.memory_service,
        "get_recent_context",
        lambda *_args: (history, {}),
    )
    monkeypatch.setattr(chat_service, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_service, "generate_reply", fake_generate_reply)
    return retrieval_queries, model_calls


def test_history_recall_skips_retrieval_and_keeps_conversation(monkeypatch):
    message = "Quel était le deuxième parcours que tu as cité ?"
    history = [
        {"role": "user", "content": "Quels sont les parcours de spécialisation ?"},
        {
            "role": "assistant",
            "content": (
                "1. Génie Logiciel et Informatique Décisionnelle (GLID)\n"
                "2. Science des Données et Intelligence Artificielle (SDIA)\n"
                "3. Administration Réseaux et Sécurité Informatique (ARSI)\n"
                "Source [1] : Plan d'études."
            ),
            "sources": [
                {
                    "source_id": "source-1",
                    "title": "Plan d'études - Génie Informatique",
                    "origin": "iit-genie-informatique-curriculum.md",
                    "page": None,
                }
            ],
        },
        {"role": "user", "content": message},
    ]
    retrieval_queries, model_calls = _configure_chat(monkeypatch, history)

    response = asyncio.run(chat_service.send_message(ChatRequest(message=message), "guest-id"))

    assert retrieval_queries == []
    assert response.sources == []
    assert response.reply == (
        "Le deuxième parcours que j'ai cité était : "
        "Science des Données et Intelligence Artificielle (SDIA)"
    )
    assert model_calls == []


def test_history_citation_recall_skips_retrieval(monkeypatch):
    message = "Quel document as-tu cité comme source dans ta réponse précédente ?"
    history = [
        {
            "role": "assistant",
            "content": "J'ai cité la source [3].",
            "sources": [
                {
                    "source_id": f"source-{index}",
                    "title": title,
                    "origin": f"document-{index}.md",
                    "page": None,
                }
                for index, title in enumerate(
                    ("Brochure", "Admission", "Plan d'études - Génie Informatique"),
                    start=1,
                )
            ],
        },
        {"role": "user", "content": message},
    ]
    retrieval_queries, model_calls = _configure_chat(monkeypatch, history)

    response = asyncio.run(chat_service.send_message(ChatRequest(message=message), "guest-id"))

    assert retrieval_queries == []
    assert response.sources == []
    assert response.reply == (
        "Dans ma réponse précédente, j'ai cité : "
        "[3] Plan d'études - Génie Informatique."
    )
    assert model_calls == []


def test_first_answer_citation_recall_does_not_expose_metadata(monkeypatch):
    message = "Quel document as-tu cité dans ta première réponse ?"
    history = [
        {
            "role": "assistant",
            "content": "Les parcours sont GLID, SDIA et ARSI. Source [3].",
            "sources": [
                {"title": "Brochure", "origin": "brochure.md"},
                {"title": "Admission", "origin": "admission.md"},
                {
                    "title": "Plan d'études - Génie Informatique",
                    "origin": "curriculum.md",
                },
            ],
        },
        {"role": "user", "content": "Quel était le deuxième parcours ?"},
        {"role": "assistant", "content": "Le deuxième était SDIA.", "sources": []},
        {"role": "user", "content": message},
    ]
    retrieval_queries, model_calls = _configure_chat(monkeypatch, history)

    response = asyncio.run(chat_service.send_message(ChatRequest(message=message), "guest-id"))

    assert retrieval_queries == []
    assert response.reply == (
        "Dans ma première réponse, j'ai cité : "
        "[3] Plan d'études - Génie Informatique."
    )
    assert "Internal metadata" not in response.reply
    assert model_calls == []


def test_factual_followup_still_uses_retrieval(monkeypatch):
    message = "Parmi ces parcours, lequel concerne l'intelligence artificielle ?"
    history = [
        {"role": "assistant", "content": "Les parcours sont GLID, SDIA et ARSI."},
        {"role": "user", "content": message},
    ]
    retrieval_queries, _ = _configure_chat(monkeypatch, history)

    response = asyncio.run(chat_service.send_message(ChatRequest(message=message), "guest-id"))

    assert retrieval_queries == [message]
    assert len(response.sources) == 1


def test_new_ordinal_question_is_not_treated_as_history_recall(monkeypatch):
    message = "Quel est le deuxième parcours disponible dans ce programme ?"
    history = [
        {"role": "assistant", "content": "1. GLID\n2. SDIA\n3. ARSI"},
        {"role": "user", "content": message},
    ]
    retrieval_queries, model_calls = _configure_chat(monkeypatch, history)

    response = asyncio.run(chat_service.send_message(ChatRequest(message=message), "guest-id"))

    assert retrieval_queries == [message]
    assert len(model_calls) == 1
    assert len(response.sources) == 1
