"""Routes « Candidats » : à coder par Membres 2 et 4. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/candidates", tags=["Candidats"])


@router.get("/me", summary="Consulter son dossier")
def get_me():
    # TODO (Membres 2 et 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.put("/me", summary="Modifier son dossier")
def put_me():
    # TODO (Membres 2 et 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/me/profile", summary="Profil d'orientation")
def get_me_profile():
    # TODO (Membres 2 et 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("", summary="Liste des candidats (responsables)")
def get_root():
    # TODO (Membres 2 et 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/{candidate_id}", summary="Dossier d'un candidat")
def get_candidate_id():
    # TODO (Membres 2 et 4) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
