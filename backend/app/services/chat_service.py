from collections import OrderedDict
from threading import Lock
from uuid import uuid4

from app.agents.language import CONFIDENT_THRESHOLD, detect_language
from app.agents.prompts import SYSTEM_PROMPT
from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_service import generate_reply
from app.services.rag_service import RetrievedChunk, retrieve

MAX_SESSIONS = 1000
MAX_HISTORY_MESSAGES = 12


class _SessionStore:
    def __init__(self) -> None:
        self._sessions: OrderedDict[str, list[dict[str, str]]] = OrderedDict()
        self._lock = Lock()

    def history(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            messages = self._sessions.get(session_id, [])
            if messages:
                self._sessions.move_to_end(session_id)
            return list(messages)

    def append(self, session_id: str, user_message: str, assistant_message: str) -> None:
        with self._lock:
            messages = self._sessions.setdefault(session_id, [])
            messages.extend([
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ])
            del messages[:-MAX_HISTORY_MESSAGES]
            self._sessions.move_to_end(session_id)
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)


_sessions = _SessionStore()


async def send_message(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid4())
    detection = detect_language(request.message)
    settings = get_settings()
    system_prompt = SYSTEM_PROMPT
    if detection.confidence < CONFIDENT_THRESHOLD:
        system_prompt += (
            "\nThe user's language could not be identified confidently. Do not guess "
            "what they mean; politely ask them to rephrase in French."
        )
    else:
        system_prompt += (
            f"\nDetected user language: {detection.language}. "
            "Use this as a hint and preserve code-switching when appropriate."
        )
    sources: list[RetrievedChunk] = []
    if settings.rag_enabled:
        sources = await retrieve(request.message, settings=settings)
        if sources:
            excerpts = "\n\n".join(
                f"[{index}] Source: {source.title}; file: {source.origin}; "
                f"page: {source.page if source.page is not None else 'n/a'}\n"
                f"<excerpt>{source.content}</excerpt>"
                for index, source in enumerate(sources, start=1)
            )
            system_prompt += (
                "\nUse the following retrieved official-document excerpts as "
                "evidence. Cite supporting excerpts as [1], [2], etc. If they "
                "do not answer the question, say so and do not infer missing facts.\n\n"
                f"<retrieved_sources>\n{excerpts}\n</retrieved_sources>"
            )
        else:
            system_prompt += (
                "\nNo relevant official-document excerpts were found for this "
                "question. Do not answer IIT/ISB-specific factual questions from "
                "memory; explain that the school must confirm the information."
            )
    else:
        system_prompt += (
            "\nThe official-document retrieval system is disabled. Do not answer "
            "IIT/ISB-specific factual questions as verified facts."
        )
    messages = [
        {"role": "system", "content": system_prompt},
        *_sessions.history(session_id),
        {"role": "user", "content": request.message},
    ]
    reply = await generate_reply(messages)
    _sessions.append(session_id, request.message, reply)
    return ChatResponse(
        session_id=session_id,
        reply=reply,
        language=detection.language,
        sources=[
            {
                "source_id": source.source_id,
                "title": source.title,
                "origin": source.origin,
                "page": source.page,
            }
            for source in sources
        ],
    )
