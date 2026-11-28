"""Staff-managed official document uploads, versions, publication, and access scope."""

import asyncio
from io import BytesIO
import uuid

import pytest
from docx import Document as WordDocument

from app.core.config import get_settings
from app.services import rag_service
from app.services import document_storage
from tests.helpers import API, IIT, ISB, make_program

pytestmark = pytest.mark.usefixtures("catalog_cleanup")


@pytest.fixture
def document_context(client, db, tmp_path, monkeypatch):
    institution_id = db.execute("SELECT id FROM institution WHERE code = 'IIT'").fetchone()[0]
    user_id = db.execute(
        """INSERT INTO app_user (role, institution_id, first_name, last_name, email, password_hash)
           VALUES ('iit_manager', %s, 'Document', 'Manager', %s, 'test')
           RETURNING id""",
        (institution_id, f"test-{uuid.uuid4().hex}@smartcampus.test"),
    ).fetchone()[0]
    manager_headers = {"X-Dev-Role": "iit_manager", "X-Dev-User-Id": str(user_id)}
    program = make_program(client, headers=manager_headers)

    settings = get_settings().model_copy(update={
        "documents_storage_dir": str(tmp_path),
        "document_max_upload_bytes": 100,
    })
    monkeypatch.setattr(document_storage, "get_settings", lambda: settings)
    yield {"db": db, "headers": manager_headers, "program": program, "storage": tmp_path}

    db.execute("DELETE FROM document_source WHERE created_by_id = %s", (user_id,))
    db.execute("DELETE FROM app_user WHERE id = %s", (user_id,))


def upload_document(client, context, *, filename="handbook.pdf", content=b"%PDF-1.7\nfirst version"):
    return client.post(
        f"{API}/documents",
        headers=context["headers"],
        data={
            "title": "Guide officiel",
            "doc_type": "regulation",
            "program_id": context["program"]["id"],
            "description": "Informations de référence",
            "language": "fr",
        },
        files={"file": (filename, content, "application/octet-stream")},
    )


def test_document_upload_metadata_version_publish_download_and_soft_delete(client, document_context):
    context = document_context
    response = upload_document(client, context, filename="../../handbook.pdf")
    assert response.status_code == 201, response.text
    document = response.json()
    document_id = document["id"]
    assert document["title"] == "Guide officiel"
    assert document["doc_type"] == "regulation"
    assert document["program_id"] == context["program"]["id"]
    assert document["status"] == "draft"
    assert document["original_filename"] == "handbook.pdf"
    assert document["current_version_number"] == 1
    listed = client.get(
        f"{API}/documents",
        headers=context["headers"],
        params={"program_id": context["program"]["id"], "status": "draft"},
    ).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == document_id

    first_version = client.get(f"{API}/documents/{document_id}/versions", headers=context["headers"]).json()[0]
    assert first_version["version_number"] == 1
    assert first_version["is_current"] is True
    assert first_version["original_filename"] == "handbook.pdf"
    first_file = context["storage"] / document_id / f"{first_version['id']}.pdf"
    assert first_file.read_bytes() == b"%PDF-1.7\nfirst version"
    downloaded = client.get(f"{API}/documents/{document_id}/download", headers=context["headers"])
    assert downloaded.status_code == 200
    assert downloaded.content == first_file.read_bytes()

    update = client.patch(
        f"{API}/documents/{document_id}",
        headers=context["headers"],
        json={"title": "Guide des études", "doc_type": "brochure"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["title"] == "Guide des études"
    assert update.json()["doc_type"] == "brochure"

    published_v1 = client.post(
        f"{API}/documents/{document_id}/versions/{first_version['id']}/publish",
        headers=context["headers"],
    )
    assert published_v1.status_code == 200
    assert published_v1.json()["status"] == "active"

    version_response = client.post(
        f"{API}/documents/{document_id}/versions",
        headers=context["headers"],
        data={"language": "fr"},
        files={"file": ("handbook-v2.txt", b"second version", "text/plain")},
    )
    assert version_response.status_code == 201, version_response.text
    version = version_response.json()
    assert version["version_number"] == 2
    assert version["is_current"] is False
    still_published = client.get(f"{API}/documents/{document_id}", headers=context["headers"]).json()
    assert still_published["status"] == "active"
    assert still_published["current_version_id"] == first_version["id"]

    published = client.post(
        f"{API}/documents/{document_id}/versions/{version['id']}/publish",
        headers=context["headers"],
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "active"
    assert published.json()["current_version_id"] == version["id"]
    assert published.json()["original_filename"] == "handbook-v2.txt"
    downloaded = client.get(f"{API}/documents/{document_id}/download", headers=context["headers"])
    assert downloaded.status_code == 200
    assert downloaded.content == b"second version"
    historical_download = client.get(
        f"{API}/documents/{document_id}/versions/{first_version['id']}/download",
        headers=context["headers"],
    )
    assert historical_download.status_code == 200
    assert historical_download.content == b"%PDF-1.7\nfirst version"
    assert client.get(f"{API}/documents/{document_id}/versions", headers=context["headers"]).json()[0]["is_current"]

    duplicate = client.post(
        f"{API}/documents/{document_id}/versions",
        headers=context["headers"],
        files={"file": ("copy.txt", b"second version", "text/plain")},
    )
    assert duplicate.status_code == 409
    assert len(list(context["storage"].rglob("*.txt"))) == 1

    removed = client.delete(f"{API}/documents/{document_id}", headers=context["headers"])
    assert removed.status_code == 204
    details = client.get(f"{API}/documents/{document_id}", headers=context["headers"]).json()
    assert details["status"] == "deleted"
    assert details["deleted_at"]
    assert first_file.exists()


def test_document_routes_enforce_staff_role_and_institution_scope(client, document_context):
    context = document_context
    created = upload_document(client, context)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    isb_program = make_program(client, headers=ISB, institution_id=str(
        context["db"].execute("SELECT id FROM institution WHERE code = 'ISB'").fetchone()[0]))

    assert client.get(f"{API}/documents/{document_id}").status_code == 401
    assert client.get(f"{API}/documents/{document_id}", headers={"X-Dev-Role": "candidate"}).status_code == 403
    assert client.get(f"{API}/documents", headers={"X-Dev-Role": "direction"}).status_code == 200
    assert client.patch(f"{API}/documents/{document_id}", headers={"X-Dev-Role": "direction"},
                        json={"title": "Interdit"}).status_code == 403
    assert client.delete(f"{API}/documents/{document_id}", headers=IIT).status_code == 403
    assert client.post(f"{API}/documents", data={}, files={}).status_code == 401
    assert client.post(f"{API}/documents", headers={"X-Dev-Role": "direction"}, data={}, files={}).status_code == 403
    assert client.post(
        f"{API}/documents/{document_id}/versions",
        headers={"X-Dev-Role": "candidate"},
        files={"file": ("copy.txt", b"no access", "text/plain")},
    ).status_code == 403
    assert client.get(f"{API}/documents/{document_id}", headers=ISB).status_code == 403
    assert client.patch(f"{API}/documents/{document_id}", headers=context["headers"],
                        json={"program_id": isb_program["id"]}).status_code == 403
    assert client.delete(f"{API}/documents/{document_id}", headers=ISB).status_code == 403


def test_document_upload_rejects_unsupported_invalid_and_oversized_files(client, document_context):
    context = document_context
    blank_title = client.post(
        f"{API}/documents",
        headers=context["headers"],
        data={"title": "   ", "doc_type": "regulation", "program_id": context["program"]["id"]},
        files={"file": ("guide.pdf", b"%PDF-1.7\n", "application/pdf")},
    )
    assert blank_title.status_code == 422

    unsupported = upload_document(client, context, filename="guide.exe", content=b"not allowed")
    assert unsupported.status_code == 415

    invalid_pdf = upload_document(client, context, content=b"not actually a pdf")
    assert invalid_pdf.status_code == 415

    invalid_text = upload_document(client, context, filename="guide.txt", content=b"\xff")
    assert invalid_text.status_code == 415

    oversized = upload_document(client, context, content=b"%PDF-" + b"x" * 101)
    assert oversized.status_code == 413
    assert client.get(f"{API}/documents", headers=context["headers"]).json()["total"] == 0
    assert not [path for path in context["storage"].rglob("*") if path.is_file()]


def test_rag_returns_only_published_current_document_versions(
    client, document_context, tmp_path, monkeypatch
):
    context = document_context
    knowledge_base = tmp_path / "knowledge_base"
    knowledge_base.mkdir()
    (knowledge_base / "baseline.txt").write_text("General public reference.", encoding="utf-8")

    storage_settings = get_settings().model_copy(update={
        "documents_storage_dir": str(context["storage"]),
        "document_max_upload_bytes": 1_000_000,
    })
    monkeypatch.setattr(document_storage, "get_settings", lambda: storage_settings)
    docx = WordDocument()
    docx.add_heading("Observatory publication", level=1)
    docx.add_paragraph("Published sentinel information for the observatory.")
    docx_file = BytesIO()
    docx.save(docx_file)
    published = upload_document(
        client,
        context,
        filename="published-only.docx",
        content=docx_file.getvalue(),
    ).json()
    draft = upload_document(
        client,
        context,
        filename="draft-only.txt",
        content=b"Draft sentinel information for the observatory.",
    ).json()
    published_version = context["db"].execute(
        "SELECT current_version_id FROM document_source WHERE id = %s",
        (published["id"],),
    ).fetchone()[0]
    publication = client.post(
        f"{API}/documents/{published['id']}/versions/{published_version}/publish",
        headers=context["headers"],
    )
    assert publication.status_code == 200, publication.text

    async def fake_embeddings(texts, *, settings):
        return [[1.0, *([0.0] * 767)] for _ in texts]

    monkeypatch.setattr(rag_service, "embed_texts", fake_embeddings)
    settings = get_settings().model_copy(update={
        "documents_storage_dir": str(context["storage"]),
        "rag_documents_dir": str(knowledge_base),
        "rag_top_k": 10,
        "rag_min_similarity": -1,
    })
    document_ids = (uuid.UUID(published["id"]), uuid.UUID(draft["id"]))
    try:
        asyncio.run(rag_service.ingest_documents(settings=settings))

        results = asyncio.run(
            rag_service.retrieve("observatory sentinel information", settings=settings)
        )
        assert any(
            result.origin == "published-only.docx"
            and "# Observatory publication" in result.content
            and "Published sentinel information" in result.content
            for result in results
        )
        assert all(result.origin != "draft-only.txt" for result in results)

        context["db"].execute(
            "UPDATE document_source SET status = 'deleted', deleted_at = now() WHERE id = %s",
            (published["id"],),
        )
        results_after_removal = asyncio.run(
            rag_service.retrieve("observatory sentinel information", settings=settings)
        )
        assert all(result.origin != "published-only.docx" for result in results_after_removal)
    finally:
        has_document_id = context["db"].execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'rag_chunks'
                  AND column_name = 'document_id'
            )
            """
        ).fetchone()[0]
        if has_document_id:
            context["db"].execute(
                "DELETE FROM rag_chunks WHERE document_id = ANY(%s)",
                (list(document_ids),),
            )
