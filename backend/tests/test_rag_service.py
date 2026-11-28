import asyncio
from contextlib import nullcontext
from unittest.mock import MagicMock

from app.core.config import Settings
from app.services import rag_service


def test_chunk_text_produces_overlapping_bounded_chunks():
    chunks = rag_service.chunk_text("x" * 2500, size=1200, overlap=180)

    assert len(chunks) == 3
    assert all(len(chunk) <= 1200 for chunk in chunks)
    assert chunks[0][-180:] == chunks[1][:180]
    assert chunks[1][-180:] == chunks[2][:180]


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
