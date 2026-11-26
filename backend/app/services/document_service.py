"""CRUD, versioning, access scope, and audit for official documents."""

import logging
from uuid import UUID, uuid4

import psycopg

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import Actor
from app.schemas.common import Page
from app.schemas.document import DocumentOut, DocumentStatus, DocumentType, DocumentUpdate, DocumentVersionOut
from app.services.catalog_service import ensure_can_manage_program
from app.services.db_utils import audit, translate_db_errors
from app.services.document_storage import StoredUpload, remove_stored_file, resolve_stored_file, store_upload

logger = logging.getLogger(__name__)

DOCUMENT_SELECT = """
SELECT d.id, d.institution_id, i.code AS school, d.program_id, p.code AS program_code,
       p.name AS program_name, d.title, d.description, d.doc_type, d.status, d.original_filename,
       d.current_version_id, v.version_number AS current_version_number, v.mime_type AS current_mime_type,
       v.size_bytes AS current_size_bytes, v.checksum_sha256 AS current_checksum_sha256,
       v.uploaded_at AS current_uploaded_at, d.created_by_id, d.created_at, d.updated_at, d.deleted_at
"""
DOCUMENT_FROM = """
FROM document_source d
JOIN program p ON p.id = d.program_id
JOIN institution i ON i.id = d.institution_id
LEFT JOIN document_version v ON v.id = d.current_version_id
"""


def _require_user_id(actor: Actor) -> UUID:
    if actor.user_id is None:
        raise ForbiddenError("Un compte du personnel authentifié est requis pour gérer les documents.")
    return actor.user_id


def _document_row(conn: psycopg.Connection, document_id: UUID, *, lock: bool = False) -> dict:
    suffix = " FOR UPDATE OF d" if lock else ""
    row = conn.execute(
        f"SELECT d.id, d.institution_id, d.program_id, d.status, d.current_version_id, d.title "
        f"FROM document_source d WHERE d.id = %s{suffix}",
        (document_id,),
    ).fetchone()
    if not row:
        raise NotFoundError("Document introuvable.")
    return row


def _ensure_read_access(actor: Actor, document: dict) -> None:
    institution_id = document["institution_id"]
    if actor.is_manager and institution_id != actor.institution_id:
        raise ForbiddenError("Ce document appartient à une autre école.")


def _ensure_write_access(actor: Actor, document: dict) -> None:
    if not actor.can_manage_institution(document["institution_id"]):
        raise ForbiddenError("Vous ne pouvez gérer que les documents de votre école.")


def _fetch_document(conn: psycopg.Connection, document_id: UUID) -> DocumentOut:
    row = conn.execute(
        f"{DOCUMENT_SELECT}{DOCUMENT_FROM} WHERE d.id = %s",
        (document_id,),
    ).fetchone()
    if not row:
        raise NotFoundError("Document introuvable.")
    return DocumentOut(**row)


def list_documents(
    conn: psycopg.Connection,
    actor: Actor,
    *,
    program_id: UUID | None = None,
    doc_type: DocumentType | None = None,
    status: DocumentStatus | None = None,
    q: str | None = None,
    page: int = 1,
    size: int = 20,
) -> Page[DocumentOut]:
    conditions = []
    params: list = []
    if actor.is_manager:
        conditions.append("d.institution_id = %s")
        params.append(actor.institution_id)
    if program_id:
        conditions.append("d.program_id = %s")
        params.append(program_id)
    if doc_type:
        conditions.append("d.doc_type = %s")
        params.append(doc_type)
    if status:
        conditions.append("d.status = %s")
        params.append(status)
    if q:
        conditions.append("(d.title ILIKE %s OR d.description ILIKE %s OR p.name ILIKE %s "
                          "OR d.original_filename ILIKE %s)")
        search = f"%{q.strip()}%"
        params.extend([search] * 4)

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    total = conn.execute(f"SELECT count(*) AS n {DOCUMENT_FROM}{where}", params).fetchone()["n"]
    rows = conn.execute(
        f"{DOCUMENT_SELECT}{DOCUMENT_FROM}{where} ORDER BY d.updated_at DESC, d.id "
        "LIMIT %s OFFSET %s",
        [*params, size, (page - 1) * size],
    ).fetchall()
    return Page[DocumentOut](items=[DocumentOut(**row) for row in rows], total=total, page=page, size=size)


def get_document(conn: psycopg.Connection, actor: Actor, document_id: UUID) -> DocumentOut:
    document = _document_row(conn, document_id)
    _ensure_read_access(actor, document)
    return _fetch_document(conn, document_id)


def list_versions(conn: psycopg.Connection, actor: Actor, document_id: UUID) -> list[DocumentVersionOut]:
    document = _document_row(conn, document_id)
    _ensure_read_access(actor, document)
    rows = conn.execute(
        """
        SELECT v.id, v.document_id, v.version_number, v.original_filename, v.mime_type, v.size_bytes,
               v.checksum_sha256, v.language, v.uploaded_by_id, v.uploaded_at,
               (v.id = d.current_version_id) AS is_current
          FROM document_version v
          JOIN document_source d ON d.id = v.document_id
         WHERE v.document_id = %s
         ORDER BY v.version_number DESC
        """,
        (document_id,),
    ).fetchall()
    return [DocumentVersionOut(**row) for row in rows]


def _cleanup_upload(upload: StoredUpload) -> None:
    try:
        remove_stored_file(upload.storage_path)
    except OSError:
        logger.exception("Could not remove uncommitted uploaded file at %s", upload.storage_path)


def create_document(
    conn: psycopg.Connection,
    actor: Actor,
    *,
    program_id: UUID,
    title: str,
    doc_type: DocumentType,
    description: str | None,
    language: str | None,
    file,
) -> DocumentOut:
    user_id = _require_user_id(actor)
    institution_id = ensure_can_manage_program(conn, actor, program_id)
    document_id, version_id = uuid4(), uuid4()
    stored = store_upload(file, document_id, version_id)
    try:
        with translate_db_errors(), conn.transaction():
            conn.execute(
                """
                INSERT INTO document_source
                    (id, institution_id, program_id, title, description, doc_type, original_filename,
                     status, created_by_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft', %s)
                """,
                (document_id, institution_id, program_id, title, description, doc_type,
                 stored.original_filename, user_id),
            )
            conn.execute(
                """
                INSERT INTO document_version
                    (id, document_id, version_number, storage_path, original_filename, mime_type,
                     size_bytes, checksum_sha256, language, uploaded_by_id)
                VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s, %s)
                """,
                (version_id, document_id, stored.storage_path, stored.original_filename, stored.mime_type,
                 stored.size_bytes, stored.checksum_sha256, language, user_id),
            )
            conn.execute(
                "UPDATE document_source SET current_version_id = %s WHERE id = %s",
                (version_id, document_id),
            )
            audit(conn, actor, "document.create", "document_source", document_id,
                  {"program_id": program_id, "version_id": version_id, "filename": stored.original_filename})
    except Exception:
        _cleanup_upload(stored)
        raise
    return _fetch_document(conn, document_id)


def update_document(
    conn: psycopg.Connection,
    actor: Actor,
    document_id: UUID,
    body: DocumentUpdate,
) -> DocumentOut:
    _require_user_id(actor)
    changes = body.changes()
    with conn.transaction():
        document = _document_row(conn, document_id, lock=True)
        _ensure_write_access(actor, document)
        if document["status"] == "deleted":
            raise ConflictError("Un document retiré ne peut plus être modifié.")

        updates = {}
        if "program_id" in changes and changes["program_id"] != document["program_id"]:
            institution_id = ensure_can_manage_program(conn, actor, changes["program_id"])
            updates["program_id"] = changes["program_id"]
            updates["institution_id"] = institution_id
        for field in ("title", "description", "doc_type"):
            if field in changes:
                updates[field] = changes[field]

        assignments = ", ".join(f"{field} = %s" for field in updates)
        if assignments:
            conn.execute(
                f"UPDATE document_source SET {assignments} WHERE id = %s",
                [*updates.values(), document_id],
            )
        audit(conn, actor, "document.update", "document_source", document_id, changes)
    return _fetch_document(conn, document_id)


def add_version(
    conn: psycopg.Connection,
    actor: Actor,
    document_id: UUID,
    *,
    language: str | None,
    file,
) -> DocumentVersionOut:
    user_id = _require_user_id(actor)
    document = _document_row(conn, document_id)
    _ensure_write_access(actor, document)
    if document["status"] == "deleted":
        raise ConflictError("Impossible d'ajouter une version à un document retiré.")

    version_id = uuid4()
    stored = store_upload(file, document_id, version_id)
    try:
        with translate_db_errors(), conn.transaction():
            document = _document_row(conn, document_id, lock=True)
            _ensure_write_access(actor, document)
            if document["status"] == "deleted":
                raise ConflictError("Impossible d'ajouter une version à un document retiré.")
            duplicate = conn.execute(
                "SELECT 1 FROM document_version WHERE document_id = %s AND checksum_sha256 = %s",
                (document_id, stored.checksum_sha256),
            ).fetchone()
            if duplicate:
                raise ConflictError("Ce fichier existe déjà dans l'historique du document.")
            version_number = conn.execute(
                "SELECT coalesce(max(version_number), 0) + 1 AS next_version "
                "FROM document_version WHERE document_id = %s",
                (document_id,),
            ).fetchone()["next_version"]
            conn.execute(
                """
                INSERT INTO document_version
                    (id, document_id, version_number, storage_path, original_filename, mime_type,
                     size_bytes, checksum_sha256, language, uploaded_by_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (version_id, document_id, version_number, stored.storage_path, stored.original_filename,
                 stored.mime_type, stored.size_bytes, stored.checksum_sha256, language, user_id),
            )
            audit(conn, actor, "document.version.upload", "document_source", document_id,
                  {"version_id": version_id, "version_number": version_number,
                   "filename": stored.original_filename})
    except Exception:
        _cleanup_upload(stored)
        raise
    return _fetch_version(conn, document_id, version_id)


def _fetch_version(conn: psycopg.Connection, document_id: UUID, version_id: UUID) -> DocumentVersionOut:
    row = conn.execute(
        """
        SELECT v.id, v.document_id, v.version_number, v.original_filename, v.mime_type, v.size_bytes,
               v.checksum_sha256, v.language, v.uploaded_by_id, v.uploaded_at,
               (v.id = d.current_version_id) AS is_current
          FROM document_version v
          JOIN document_source d ON d.id = v.document_id
         WHERE v.document_id = %s AND v.id = %s
        """,
        (document_id, version_id),
    ).fetchone()
    if not row:
        raise NotFoundError("Version du document introuvable.")
    return DocumentVersionOut(**row)


def publish_version(
    conn: psycopg.Connection,
    actor: Actor,
    document_id: UUID,
    version_id: UUID,
) -> DocumentOut:
    _require_user_id(actor)
    with conn.transaction():
        document = _document_row(conn, document_id, lock=True)
        _ensure_write_access(actor, document)
        if document["status"] == "deleted":
            raise ConflictError("Un document retiré ne peut pas être publié.")
        version = conn.execute(
            "SELECT original_filename FROM document_version WHERE id = %s AND document_id = %s",
            (version_id, document_id),
        ).fetchone()
        if not version:
            raise NotFoundError("Version du document introuvable.")
        conn.execute(
            """
            UPDATE document_source
               SET current_version_id = %s, original_filename = %s, status = 'active', deleted_at = NULL
             WHERE id = %s
            """,
            (version_id, version["original_filename"], document_id),
        )
        audit(conn, actor, "document.version.publish", "document_source", document_id,
              {"version_id": version_id})
    return _fetch_document(conn, document_id)


def delete_document(conn: psycopg.Connection, actor: Actor, document_id: UUID) -> None:
    _require_user_id(actor)
    with conn.transaction():
        document = _document_row(conn, document_id, lock=True)
        _ensure_write_access(actor, document)
        if document["status"] == "deleted":
            raise ConflictError("Le document a déjà été retiré.")
        conn.execute(
            "UPDATE document_source SET status = 'deleted', deleted_at = now() WHERE id = %s",
            (document_id,),
        )
        audit(conn, actor, "document.delete", "document_source", document_id,
              {"previous_status": document["status"]})


def document_file(
    conn: psycopg.Connection,
    actor: Actor,
    document_id: UUID,
    version_id: UUID | None = None,
) -> tuple[str, str, str]:
    document = _document_row(conn, document_id)
    _ensure_read_access(actor, document)
    selected_version_id = version_id or document["current_version_id"]
    if selected_version_id is None:
        raise NotFoundError("Aucune version n'est associée à ce document.")
    version = conn.execute(
        """
        SELECT storage_path, mime_type, original_filename
          FROM document_version
         WHERE id = %s AND document_id = %s
        """,
        (selected_version_id, document_id),
    ).fetchone()
    if not version:
        raise NotFoundError("Version du document introuvable.")
    path = resolve_stored_file(version["storage_path"])
    return str(path), version["mime_type"], version["original_filename"]
