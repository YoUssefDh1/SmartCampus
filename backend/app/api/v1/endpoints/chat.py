"""Routes « Conversations » : mémoire temporaire visiteur (SA-26) et réponse LLM (SA-30)."""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.errors import ForbiddenError, NotFoundError, NotImplementedYetError
from app.core.security import get_current_guest_session
from app.db.session import get_dict_connection
from app.schemas.chat import (ChatHistoryResponse, ChatRequest, ChatResponse,
                              ChatSessionListResponse)
from app.services import memory_service
from app.services.chat_service import send_message
from app.services.guest_service import GuestSession

router = APIRouter(prefix="/chat", tags=["Conversations"])


@router.post("/message", response_model=ChatResponse, summary="Envoyer un message texte")
async def post_message(request: ChatRequest,
                       guest: GuestSession = Depends(get_current_guest_session)) -> ChatResponse:
    return await send_message(request, guest.id)


@router.post("/audio", summary="Envoyer un message vocal")
def post_audio():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/sessions", response_model=ChatSessionListResponse, summary="Lister ses conversations")
def get_sessions(guest: GuestSession = Depends(get_current_guest_session)) -> ChatSessionListResponse:
    with get_dict_connection() as connection:
        rows = memory_service.list_guest_conversations(connection, guest.id)
    return ChatSessionListResponse(items=rows, total=len(rows))


@router.get("/sessions/{session_id}/history", response_model=ChatHistoryResponse, summary="Historique")
def get_sessions_session_id_history(
    session_id: UUID,
    guest: GuestSession = Depends(get_current_guest_session),
) -> ChatHistoryResponse:
    """Historique d'une conversation : strictement limité à la session visiteur du jeton."""
    with get_dict_connection() as connection:
        conversation = memory_service.get_conversation(connection, str(session_id))
        if conversation is None:
            raise NotFoundError("Conversation introuvable.")
        if str(conversation["guest_session_id"] or "") != guest.id:
            raise ForbiddenError("Accès refusé : la conversation ne fait pas partie de votre session visiteur.")
        messages = memory_service.list_messages(connection, str(session_id))

    return ChatHistoryResponse(
        id=conversation["id"],
        status=conversation["status"],
        language=conversation["language"],
        started_at=conversation["started_at"],
        last_message_at=conversation["last_message_at"],
        profile_draft=conversation["profile_draft"],
        guest_session_id=conversation["guest_session_id"],
        messages=messages,
        total_messages=len(messages),
    )


@router.get("/sessions/{session_id}/summary", summary="Résumé du parcours")
def get_sessions_session_id_summary():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
