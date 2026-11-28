import asyncio
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from docx import Document as WordDocument

from app.core.config import Settings
from app.services import rag_service


def test_chunk_text_produces_overlapping_bounded_chunks():
    chunks = rag_service.chunk_text("x" * 2500, size=1200, overlap=180)

    assert len(chunks) == 3
    assert all(len(chunk) <= 1200 for chunk in chunks)
    assert chunks[0][-180:] == chunks[1][:180]
    assert chunks[1][-180:] == chunks[2][:180]


def test_chunk_text_keeps_sentences_and_markdown_headings_together():
    text = (
        "## Admission\n"
        "Les candidatures sont ouvertes. Les dossiers complets sont obligatoires.\n\n"
        "## Frais\n"
        "Les montants annuels sont publiés. Le paiement se fait en deux étapes."
    )

    chunks = rag_service.chunk_text(text, size=70, overlap=0)

    assert chunks[0] == "## Admission — Les candidatures sont ouvertes."
    assert any("Les dossiers complets sont obligatoires." in chunk for chunk in chunks)
    assert any(chunk.startswith("## Frais — ") for chunk in chunks)
    assert all(len(chunk) <= 70 for chunk in chunks)


def test_multilingual_embedding_model_uses_task_prefixes():
    settings = Settings(rag_embedding_model="nomic-embed-text-v2-moe:latest")

    assert rag_service._embedding_inputs(
        ["un document"], task="document", settings=settings
    ) == ["search_document: un document"]
    assert rag_service._embedding_inputs(
        ["une question"], task="query", settings=settings
    ) == ["search_query: une question"]


def test_rerank_promotes_exact_curriculum_match_over_similar_admission_docs():
    query = "Quelle est la durée du cycle ingénieur en génie informatique ?"
    candidates = [
        rag_service.RetrievedChunk(
            source_id="prep",
            title="iit-cycle-preparatoire-curriculum",
            origin="iit-cycle-preparatoire-curriculum.md",
            page=None,
            content="Cycle préparatoire aux grandes écoles d'ingénieurs.",
            similarity=0.698,
        ),
        rag_service.RetrievedChunk(
            source_id="admission",
            title="iit-genie-informatique-admission",
            origin="iit-genie-informatique-admission.md",
            page=None,
            content="Admission au cycle ingénieur en génie informatique.",
            similarity=0.767,
        ),
        rag_service.RetrievedChunk(
            source_id="curriculum",
            title="iit-genie-informatique-curriculum",
            origin="iit-genie-informatique-curriculum.md",
            page=None,
            content="Cycle ingénieur en génie informatique. Durée : 3 ans (6 semestres).",
            similarity=0.761,
        ),
        rag_service.RetrievedChunk(
            source_id="mechanical",
            title="iit-genie-mecanique-curriculum",
            origin="iit-genie-mecanique-curriculum.md",
            page=None,
            content=(
                "Cycle ingénieur en génie informatique. Durée : 3 ans "
                "(6 semestres)."
            ),
            similarity=0.777,
        ),
    ]

    ranked = rag_service._rerank_chunks(query, candidates, top_k=2)

    assert [chunk.origin for chunk in ranked] == [
        "iit-genie-informatique-curriculum.md",
        "iit-genie-informatique-admission.md",
    ]


def test_humanize_source_title_formats_curriculum_slug():
    assert rag_service._humanize_source_title("iit-genie-informatique-curriculum") == (
        "Plan d'études — Génie Informatique (IIT)"
    )


def test_humanize_source_title_preserves_unknown_titles():
    assert rag_service._humanize_source_title("custom-official-document") == (
        "custom-official-document"
    )


def test_document_loader_skips_its_instructions_file(tmp_path):
    (tmp_path / "README.md").write_text("Ingestion instructions", encoding="utf-8")
    (tmp_path / "official.txt").write_text("Official school content.", encoding="utf-8")

    chunks = rag_service._document_chunks(tmp_path)

    assert len(chunks) == 1
    assert chunks[0].source_path == "official.txt"
    assert chunks[0].content == "Official school content."


def test_docx_extraction_preserves_headings_paragraphs_and_tables(tmp_path):
    document = WordDocument()
    document.add_heading("Conditions d'admission", level=1)
    document.add_paragraph("Le dossier doit être complet.")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Date limite"
    table.cell(0, 1).text = "30 juin"
    path = tmp_path / "guide.docx"
    document.save(path)

    chunks = rag_service._document_chunks(tmp_path)

    assert len(chunks) == 1
    assert chunks[0].page == 0
    assert "# Conditions d'admission — Le dossier doit être complet." in chunks[0].content
    assert "Date limite | 30 juin" in chunks[0].content


def test_pdf_extraction_reports_pages_without_selectable_text(monkeypatch, tmp_path):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        pages = [FakePage("Page lisible."), FakePage("")]

        def __init__(self, _path):
            pass

    monkeypatch.setattr(rag_service, "PdfReader", FakeReader)

    with pytest.raises(rag_service.DocumentExtractionError, match=r"page\(s\) 2"):
        rag_service._read_document(tmp_path / "partiel.pdf")


def test_unreadable_pdf_reports_the_source_filename(monkeypatch, tmp_path):
    def unreadable_reader(_path):
        raise OSError("invalid file")

    monkeypatch.setattr(rag_service, "PdfReader", unreadable_reader)

    with pytest.raises(rag_service.DocumentExtractionError, match="broken.pdf"):
        rag_service._read_document(tmp_path / "broken.pdf")


def test_unreadable_docx_reports_the_source_filename(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a DOCX package")

    with pytest.raises(rag_service.DocumentExtractionError, match="broken.docx"):
        rag_service._read_document(path)


def test_ingestion_stores_all_chunks_for_a_document_in_one_replace(monkeypatch, tmp_path):
    (tmp_path / "guide.txt").write_text("A" * 25_000, encoding="utf-8")
    stores = []
    initialized_dimensions = []

    def fake_store(source_path, chunks, embeddings, _settings):
        stores.append((source_path, chunks, embeddings))

    async def fake_embed_texts(texts, *, settings):
        return [[float(index), 1.0] for index, _ in enumerate(texts)]

    monkeypatch.setattr(
        rag_service,
        "_initialize_schema",
        lambda _settings, dimensions: initialized_dimensions.append(dimensions),
    )
    monkeypatch.setattr(rag_service, "_store_document_chunks", fake_store)
    monkeypatch.setattr(rag_service, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(rag_service, "_published_document_chunks", lambda _settings: [])

    count = asyncio.run(rag_service.ingest_documents(
        settings=Settings(rag_documents_dir=str(tmp_path))
    ))

    assert count > rag_service.EMBEDDING_BATCH_SIZE
    assert len(stores) == 1
    assert stores[0][0] == "guide.txt"
    assert len(stores[0][1]) == count
    assert len(stores[0][2]) == count
    assert initialized_dimensions == [2]


def test_store_document_chunks_uses_cursor_executemany(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.transaction.return_value = nullcontext()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    monkeypatch.setattr(rag_service.psycopg, "connect", lambda _url: connection)

    chunk = rag_service.DocumentChunk(
        source_path="guide.md",
        title="Guide",
        page=0,
        chunk_index=0,
        content="Official content",
    )
    rag_service._store_document_chunks(
        "guide.md",
        [chunk],
        [[0.1, 0.2]],
        Settings(),
    )

    cursor.executemany.assert_called_once()
