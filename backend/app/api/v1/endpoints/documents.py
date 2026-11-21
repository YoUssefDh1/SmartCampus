"""Routes « Documents » : à coder par Membre 2. Contrat défini en SA-5."""
from fastapi import APIRouter

from app.core.errors import NotImplementedYetError

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", summary="Téléverser un document")
def post_root():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("", summary="Lister les documents")
def get_root():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/{document_id}", summary="Métadonnées")
def get_document_id():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/{document_id}/download", summary="Télécharger")
def get_document_id_download():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.delete("/{document_id}", summary="Supprimer")
def delete_document_id():
    # TODO (Membre 2) : remplacer par la vraie logique, via un service dans app/services/
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
