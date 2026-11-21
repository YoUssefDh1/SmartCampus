"""Routes « Conversations » : à coder par Membre 5. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/chat", tags=["Conversations"])


@router.post("/message", summary="Envoyer un message texte")
def post_message():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.post("/audio", summary="Envoyer un message vocal")
def post_audio():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/sessions", summary="Lister ses conversations")
def get_sessions():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/sessions/{session_id}/history", summary="Historique")
def get_sessions_session_id_history():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/sessions/{session_id}/summary", summary="Résumé du parcours")
def get_sessions_session_id_summary():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
