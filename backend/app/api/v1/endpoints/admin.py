"""Routes « Administration » : à coder par Membre 4. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/users", summary="Lister les comptes")
def get_users():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/logs", summary="Journaux")
def get_logs():
    # TODO (Membre 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
