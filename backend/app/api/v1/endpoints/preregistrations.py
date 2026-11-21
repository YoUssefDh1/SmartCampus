"""Routes « Préinscriptions » : à coder par Membre 2. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/preregistrations", tags=["Préinscriptions"])


@router.post("", summary="Créer la préinscription")
def post_root():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/me", summary="Consulter la sienne")
def get_me():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
