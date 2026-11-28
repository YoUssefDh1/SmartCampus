"""Orchestration du chat visiteur : mémoire PostgreSQL (SA-26) + LLM/RAG (SA-30).

Le jeton guest (SA-25) fournit l'identité ; la fenêtre glissante et le profile_draft
sont lus/écrits en base, donc la mémoire survit à un redémarrage du backend.
"""
import json
import re

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


_HISTORY_RECALL_PATTERNS = (
    re.compile(
        r"\b(?:what|which)\s+(?:did|have)\s+you\s+(?:just\s+)?(?:say|mention|cite)\b",
        re.I,
    ),
    re.compile(r"\b(?:you\s+(?:just\s+)?(?:said|mentioned|cited))\b", re.I),
    re.compile(r"\b(?:previous|earlier|last)\s+(?:answer|response|message|source)\b", re.I),
    re.compile(r"\b(?:first|initial)\s+(?:answer|response|reply)\b", re.I),
    re.compile(r"\b(?:réponse|source|message)\s+(?:précédent(?:e)?|plus haut|d'avant)\b", re.I),
    re.compile(r"\b(?:première|premiere|premier)\s+réponse\b", re.I),
    re.compile(r"\b(?:que|ce que)\s+tu\s+(?:as\s+)?(?:dit|cité|mentionné)\b", re.I),
    re.compile(r"\b(?:as-tu|tu as)\s+(?:juste\s+)?(?:dit|cité|mentionné)\b", re.I),
    re.compile(
        r"\b(?:the\s+)?(?:first|second|third|last)\s+(?:one|item|option|path|program)\b"
        r".*\b(?:you\s+)?(?:mentioned|said|cited)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:premier|première|deuxième|second|seconde|troisième|dernier|dernière)\b"
        r".*\bque tu as\s+(?:dit|cité|mentionné)\b",
        re.I,
    ),
)
_ORDINAL_PATTERNS = (
    (re.compile(r"\b(?:premier|première|first|1st)\b", re.I), 1),
    (re.compile(r"\b(?:deuxi[eè]me|seconde?|2(?:e|ème|nd)?)\b", re.I), 2),
    (re.compile(r"\b(?:troisi[eè]me|third|3(?:e|ème|rd)?)\b", re.I), 3),
)
_LIST_ITEM_PATTERN = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$")
_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_FRENCH_RECALL_MARKERS = re.compile(
    r"\b(?:quel(?:le|s|les)?|était|etait|tu|cité|cite|précédent(?:e)?|"
    r"precedent(?:e)?|première|premiere|réponse|reponse)\b",
    re.I,
)


def _is_history_recall_request(message: str) -> bool:
    return any(pattern.search(message) for pattern in _HISTORY_RECALL_PATTERNS)


def _is_prior_source_question(message: str) -> bool:
    return (
        _is_history_recall_request(message)
        and re.search(r"\b(?:source|document|citation)\b", message, re.I) is not None
    )


def _is_first_response_reference(message: str) -> bool:
    return re.search(
        r"\b(?:first|initial)\s+(?:answer|response|reply)\b|"
        r"\b(?:première|premiere|premier)\s+réponse\b",
        message,
        re.I,
    ) is not None


def _target_assistant_message(message: str, history: list[dict]) -> dict | None:
    assistant_messages = [
        row for row in history[:-1] if row.get("role") == "assistant"
    ]
    if not assistant_messages:
        return None
    if _is_first_response_reference(message):
        return assistant_messages[0]
    return assistant_messages[-1]


def _history_recall_answer(message: str, history: list[dict], language: str) -> str | None:
    if not _is_history_recall_request(message):
        return None

    target = _target_assistant_message(message, history)
    if target is None:
        return None

    if language not in {"fr", "en"}:
        previous_language = target.get("language")
        if previous_language in {"fr", "en"}:
            language = previous_language
        elif _FRENCH_RECALL_MARKERS.search(message):
            language = "fr"
        else:
            return None

    content = target.get("content", "")
    if _is_prior_source_question(message):
        response_label = (
            "ma première réponse"
            if _is_first_response_reference(message)
            else "ma réponse précédente"
        )
        source_rows = target.get("sources")
        citations = list(
            dict.fromkeys(int(value) for value in _CITATION_PATTERN.findall(content))
        )
        cited_sources = []
        if isinstance(source_rows, list):
            for citation in citations:
                if citation < 1 or citation > len(source_rows):
                    continue
                source = source_rows[citation - 1]
                if isinstance(source, dict):
                    title = source.get("title")
                    if isinstance(title, str) and title:
                        cited_sources.append(f"[{citation}] {title}")
            if not cited_sources:
                cited_sources.extend(
                    source["title"]
                    for source in source_rows
                    if isinstance(source, dict)
                    and isinstance(source.get("title"), str)
                    and source["title"].casefold() in content.casefold()
                )
        if cited_sources:
            joined = "; ".join(cited_sources)
            if language == "fr":
                return f"Dans {response_label}, j'ai cité : {joined}."
            return f"In that reply, I cited: {joined}."
        if not citations:
            if language == "fr":
                return f"Dans {response_label}, je n'ai cité aucune source."
            return "I didn't cite a source in that reply."

    for pattern, index in _ORDINAL_PATTERNS:
        if pattern.search(message):
            items = _LIST_ITEM_PATTERN.findall(content)
            if index <= len(items):
                if language == "fr":
                    ordinal = ("premier", "deuxième", "troisième")[index - 1]
                    return f"Le {ordinal} parcours que j'ai cité était : {items[index - 1]}"
                ordinal = ("first", "second", "third")[index - 1]
                return f"The {ordinal} item I mentioned was: {items[index - 1]}"
    return None


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


def _rag_directive(
    sources: list[RetrievedChunk],
    rag_enabled: bool,
    *,
    history_recall: bool = False,
) -> str:
    if history_recall:
        return (
            "\nThis is a question about earlier conversation, not a new factual "
            "question. Answer from recent conversation history only. Do not cite "
            "or rely on sources retrieved for other turns. If asked about a prior "
            "citation, report it as it appeared in the earlier assistant reply."
        )
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

    history_recall = _is_history_recall_request(request.message)
    reply = _history_recall_answer(request.message, history, detection.language)
    llm_history = memory_service.history_to_llm_messages(history)

    sources: list[RetrievedChunk] = []
    if settings.rag_enabled and not history_recall:
        sources = await retrieve(request.message, settings=settings)

    if reply is None:
        system_prompt = (SYSTEM_PROMPT + _language_directive(detection)
                         + _rag_directive(
                             sources,
                             settings.rag_enabled,
                             history_recall=history_recall,
                         )
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
