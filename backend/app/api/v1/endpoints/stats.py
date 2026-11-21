"""Routes « Statistiques » : à coder par Membre 2. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/stats", tags=["Statistiques"])


@router.get("/overview", summary="Indicateurs globaux")
def get_overview():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/funnel", summary="Taux de transformation")
def get_funnel():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
