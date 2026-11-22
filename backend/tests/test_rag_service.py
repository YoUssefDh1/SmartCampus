import asyncio

from app.core.config import Settings
from app.services import rag_service


def test_chunk_text_produces_overlapping_bounded_chunks():
    chunks = rag_service.chunk_text("x" * 2500, size=1200, overlap=180)

    assert len(chunks) == 3
    assert all(len(chunk) <= 1200 for chunk in chunks)
    assert chunks[0][-180:] == chunks[1][:180]
    assert chunks[1][-180:] == chunks[2][:180]


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

    def fake_store(source_path, chunks, embeddings, _settings):
        stores.append((source_path, chunks, embeddings))

    async def fake_embed_texts(texts, *, settings):
        return [[float(index)] for index, _ in enumerate(texts)]

    monkeypatch.setattr(rag_service, "_initialize_schema", lambda _settings: None)
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
