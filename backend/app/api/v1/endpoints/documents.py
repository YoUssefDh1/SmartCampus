"""Gestion des documents officiels IIT/ISB et de leurs versions."""

from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.core.errors import UnprocessableError
from app.core.security import CATALOG_READ_ROLES, CATALOG_WRITE_ROLES, Actor, require_roles
from app.db.session import get_db
from app.schemas.common import ErrorResponse, Page
from app.schemas.document import DocumentOut, DocumentStatus, DocumentType, DocumentUpdate, DocumentVersionOut
from app.services import document_service as svc

router = APIRouter(prefix="/documents", tags=["Documents"])

reader = require_roles(*CATALOG_READ_ROLES)
writer = require_roles(*CATALOG_WRITE_ROLES)
ERRORS = {
    404: {"model": ErrorResponse, "description": "Document ou version introuvable"},
    409: {"model": ErrorResponse, "description": "Version en doublon ou document retiré"},
    413: {"model": ErrorResponse, "description": "Fichier trop volumineux"},
    415: {"model": ErrorResponse, "description": "Format de fichier non accepté"},
}
PAGE = Query(1, ge=1)
SIZE = Query(20, ge=1, le=100)


def _clean_form_text(value: str | None) -> str | None:
    cleaned = value.strip() if value is not None else None
    return cleaned or None


def _required_form_text(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise UnprocessableError(f"Le champ {field} est obligatoire.")
    return cleaned


@router.post("", response_model=DocumentOut, status_code=201, responses=ERRORS,
             summary="Ajouter un document officiel (créé en brouillon)")
def create_document(
    title: Annotated[str, Form(min_length=1, max_length=250)],
    doc_type: Annotated[DocumentType, Form()],
    program_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    description: Annotated[str | None, Form(max_length=5000)] = None,
    language: Annotated[str | None, Form(max_length=20)] = None,
    actor: Actor = Depends(writer),
    conn: psycopg.Connection = Depends(get_db),
):
    return svc.create_document(
        conn,
        actor,
        program_id=program_id,
        title=_required_form_text(title, "title"),
        doc_type=doc_type,
        description=_clean_form_text(description),
        language=_clean_form_text(language),
        file=file,
    )


@router.get("", response_model=Page[DocumentOut], summary="Rechercher les documents")
def list_documents(
    program_id: UUID | None = None,
    doc_type: DocumentType | None = None,
    status: DocumentStatus | None = None,
    q: str | None = Query(None, max_length=200),
    page: int = PAGE,
    size: int = SIZE,
    actor: Actor = Depends(reader),
    conn: psycopg.Connection = Depends(get_db),
):
    return svc.list_documents(conn, actor, program_id=program_id, doc_type=doc_type, status=status,
                              q=q, page=page, size=size)


@router.get("/{document_id}", response_model=DocumentOut, responses=ERRORS, summary="Consulter un document")
def get_document(document_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_document(conn, actor, document_id)


@router.patch("/{document_id}", response_model=DocumentOut, responses=ERRORS, summary="Modifier les métadonnées")
def update_document(document_id: UUID, body: DocumentUpdate, actor: Actor = Depends(writer),
                    conn: psycopg.Connection = Depends(get_db)):
    return svc.update_document(conn, actor, document_id, body)


@router.get("/{document_id}/versions", response_model=list[DocumentVersionOut], responses=ERRORS,
            summary="Consulter l'historique des versions")
def list_versions(document_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.list_versions(conn, actor, document_id)


@router.post("/{document_id}/versions", response_model=DocumentVersionOut, status_code=201, responses=ERRORS,
             summary="Importer une nouvelle version (non publiée)")
def add_version(
    document_id: UUID,
    file: Annotated[UploadFile, File()],
    language: Annotated[str | None, Form(max_length=20)] = None,
    actor: Actor = Depends(writer),
    conn: psycopg.Connection = Depends(get_db),
):
    return svc.add_version(
        conn, actor, document_id, language=_clean_form_text(language), file=file
    )


@router.post("/{document_id}/versions/{version_id}/publish", response_model=DocumentOut, responses=ERRORS,
             summary="Publier une version et la rendre active")
def publish_version(document_id: UUID, version_id: UUID, actor: Actor = Depends(writer),
                    conn: psycopg.Connection = Depends(get_db)):
    return svc.publish_version(conn, actor, document_id, version_id)


@router.get("/{document_id}/download", responses=ERRORS, summary="Télécharger la version courante")
def download_document(document_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    path, mime_type, filename = svc.document_file(conn, actor, document_id)
    return FileResponse(path, media_type=mime_type, filename=filename)


@router.get("/{document_id}/versions/{version_id}/download", responses=ERRORS,
            summary="Télécharger une version précise")
def download_version(document_id: UUID, version_id: UUID, actor: Actor = Depends(reader),
                     conn: psycopg.Connection = Depends(get_db)):
    path, mime_type, filename = svc.document_file(conn, actor, document_id, version_id)
    return FileResponse(path, media_type=mime_type, filename=filename)


@router.delete("/{document_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Retirer un document (suppression logique, historique conservé)")
def delete_document(document_id: UUID, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    svc.delete_document(conn, actor, document_id)
    return Response(status_code=204)
