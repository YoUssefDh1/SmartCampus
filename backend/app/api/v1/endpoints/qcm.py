"""Routes « QCM » : à coder par Membre 5. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/qcm", tags=["QCM"])


@router.post("/generate", summary="Générer un QCM")
def post_generate():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.post("/{qcm_id}/submit", summary="Soumettre les réponses")
def post_qcm_id_submit():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/{qcm_id}/result", summary="Résultat")
def get_qcm_id_result():
    # TODO (Membre 5) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
