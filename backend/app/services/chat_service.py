"""Orchestration du chat visiteur : mémoire PostgreSQL (SA-26) + LLM/RAG (SA-30).

Le jeton guest (SA-25) fournit l'identité ; la fenêtre glissante et le profile_draft
sont lus/écrits en base, donc la mémoire survit à un redémarrage du backend.
"""
import json

from app.agents.language import CONFIDENT_THRESHOLD, LanguageDetection, detect_language
from app.agents.profile import to_chat_language
from app.agents.prompts import SYSTEM_PROMPT
from app.core.config import get_settings
from app.db.session import get_dict_connection
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import memory_service
from app.services.guest_service import check_guest_message_allowed
from app.services.llm_service import generate_reply
from app.services.rag_service import RetrievedChunk, retrieve


def _language_directive(detection: LanguageDetection) -> str:
    if detection.confidence < CONFIDENT_THRESHOLD:
        return (
            "\nThe user's language could not be identified confidently. Do not guess "
            "what they mean; politely ask them to rephrase in French."
        )
    return (
        f"\nDetected user language: {detection.language}. "
        "Use this as a hint and preserve code-switching when appropriate."
    )


def _rag_directive(sources: list[RetrievedChunk], rag_enabled: bool) -> str:
    if not rag_enabled:
        return (
            "\nThe official-document retrieval system is disabled. Do not answer "
            "IIT/ISB-specific factual questions as verified facts."
        )
    if not sources:
        return (
            "\nNo relevant official-document excerpts were found for this "
            "question. Do not answer IIT/ISB-specific factual questions from "
            "memory; explain that the school must confirm the information."
        )
    excerpts = "\n\n".join(
        f"[{index}] Source: {source.title}; file: {source.origin}; "
        f"page: {source.page if source.page is not None else 'n/a'}\n"
        f"<excerpt>{source.content}</excerpt>"
        for index, source in enumerate(sources, start=1)
    )
    return (
        "\nUse the following retrieved official-document excerpts as "
        "evidence. Cite supporting excerpts as [1], [2], etc. If they "
        "do not answer the question, say so and do not infer missing facts.\n\n"
        f"<retrieved_sources>\n{excerpts}\n</retrieved_sources>"
    )


def _profile_directive(profile_draft: dict) -> str:
    if not profile_draft:
        return ""
    return (
        "\nVisitor profile extracted so far (may be incomplete, never invent the "
        f"missing parts):\n<profile_draft>\n{json.dumps(profile_draft, ensure_ascii=False)}\n</profile_draft>"
    )


async def send_message(request: ChatRequest, guest_session_id: str) -> ChatResponse:
    settings = get_settings()
    detection = detect_language(request.message)
    chat_language = to_chat_language(detection.language)
    signals = memory_service.collect_profile_signals(request.message, detection.language)

    with get_dict_connection() as connection:
        check_guest_message_allowed(connection, guest_session_id)
        conversation = memory_service.get_or_create_conversation(
            connection, guest_session_id, request.session_id
        )
        conversation_id = str(conversation["id"])
        memory_service.save_message(connection, conversation_id, "user", request.message,
                                    language=chat_language, profile_updates=signals)
        profile_draft = memory_service.update_profile_draft(connection, conversation_id, signals)
        history, _ = memory_service.get_recent_context(connection, conversation_id)
        llm_history = memory_service.history_to_llm_messages(history)

    sources: list[RetrievedChunk] = []
    if settings.rag_enabled:
        sources = await retrieve(request.message, settings=settings)

    system_prompt = (SYSTEM_PROMPT + _language_directive(detection)
                     + _rag_directive(sources, settings.rag_enabled)
                     + _profile_directive(profile_draft))
    messages = [{"role": "system", "content": system_prompt}, *llm_history]
    reply = await generate_reply(messages)

    sources_payload = [
        {"source_id": source.source_id, "title": source.title,
         "origin": source.origin, "page": source.page}
        for source in sources
    ]
    with get_dict_connection() as connection:
        memory_service.save_message(connection, conversation_id, "assistant", reply,
                                    language=chat_language, sources=sources_payload)

    return ChatResponse(
        session_id=conversation_id,
        reply=reply,
        language=detection.language,
        sources=sources_payload,
        profile_updates=profile_draft,
    )
