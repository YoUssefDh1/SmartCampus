"""Routes « Rendez-vous » : à coder par Membres 4 et 5. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/appointments", tags=["Rendez-vous"])


@router.get("", summary="Consulter les rendez-vous")
def get_root():
    # TODO (Membres 4 et 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.post("", summary="Proposer un rendez-vous")
def post_root():
    # TODO (Membres 4 et 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.patch("/{appointment_id}", summary="Confirmer, déplacer, annuler")
def patch_appointment_id():
    # TODO (Membres 4 et 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
