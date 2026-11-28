import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from zipfile import BadZipFile

import psycopg
from docx import Document as WordDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.config import Settings, get_settings
from app.core.errors import AIUnavailableError
from app.services.embedding_service import embed_texts
from app.services.document_storage import resolve_stored_file

CHUNK_SIZE = 600
CHUNK_OVERLAP = 90
EMBEDDING_BATCH_SIZE = 16
MULTILINGUAL_EMBEDDING_MODEL = "nomic-embed-text-v2-moe"
RERANK_CANDIDATE_MULTIPLIER = 5
MIN_RERANK_CANDIDATES = 20
MAX_RERANK_CANDIDATES = 100
LEXICAL_RERANK_WEIGHT = 0.1
TITLE_RERANK_WEIGHT = 0.25
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".md", ".txt"}
_RERANK_STOPWORDS = frozenset(
    "a an and are as at au aux avec ce ces dans de des du elle en est et for from "
    "how i il in is it la le les of on or ou par pour que quelle quelles quel quels "
    "qui sur the this to un une was what when where which who with".split()
)
_SOURCE_TYPE_LABELS = {
    "admission": "Admission",
    "brochure": "Brochure",
    "curriculum": "Plan d'études",
}
_SOURCE_WORD_LABELS = {
    "cybersecurite": "Cybersécurité",
    "donnees": "Données",
    "embarques": "Embarqués",
    "energies": "Énergies",
    "genie": "Génie",
    "informatique": "Informatique",
    "ingenieur": "Ingénieur",
    "mecanique": "Mécanique",
    "preparatoire": "Préparatoire",
    "procedes": "Procédés",
    "reseaux": "Réseaux",
    "systemes": "Systèmes",
}


@dataclass(frozen=True)
class RetrievedChunk:
    source_id: str
    title: str
    origin: str
    page: int | None
    content: str
    similarity: float


@dataclass(frozen=True)
class DocumentChunk:
    source_path: str
    title: str
    page: int
    chunk_index: int
    content: str
    document_id: UUID | None = None
    document_version_id: UUID | None = None


class DocumentExtractionError(ValueError):
    """Raised when a source cannot be fully converted to searchable text."""


def chunk_text(text: str, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size must be positive and overlap must be smaller than size.")
    if not text.strip():
        return []

    segments = []
    pending_heading = None
    paragraphs = re.split(r"\n[ \t]*\n+", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    for paragraph in paragraphs:
        lines = paragraph.splitlines()
        heading = re.fullmatch(r"\s{0,3}#{1,6}\s+.+?\s*", lines[0]) if lines else None
        if heading:
            pending_heading = re.sub(r"\s+", " ", lines.pop(0)).strip()

        normalized = re.sub(r"\s+", " ", "\n".join(lines)).strip()
        if not normalized:
            continue

        sentences = [
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?…])\s+", normalized)
            if sentence.strip()
        ]
        if pending_heading:
            sentences[0] = f"{pending_heading} — {sentences[0]}"
            pending_heading = None
        segments.extend(sentences)

    if pending_heading:
        segments.append(pending_heading)

    segments = [
        piece
        for segment in segments
        for piece in _split_oversized_segment(segment, size=size, overlap=overlap)
    ]

    chunks = []
    current = []
    for segment in segments:
        if current and len(" ".join([*current, segment])) > size:
            chunks.append(" ".join(current))
            carried = []
            for previous in reversed(current):
                candidate = " ".join([previous, *carried])
                if len(candidate) > overlap:
                    break
                carried.insert(0, previous)
            current = carried
            while current and len(" ".join([*current, segment])) > size:
                current.pop(0)
        current.append(segment)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _split_oversized_segment(segment: str, *, size: int, overlap: int) -> list[str]:
    if len(segment) <= size:
        return [segment]

    pieces = []
    start = 0
    while start < len(segment):
        end = min(start + size, len(segment))
        if end < len(segment):
            boundary = segment.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        pieces.append(segment[start:end].strip())
        if end == len(segment):
            break

        next_start = max(start + 1, end - overlap)
        boundary = segment.find(" ", next_start, end)
        if boundary >= 0:
            next_start = boundary + 1
        start = next_start
    return pieces


def _embedding_inputs(texts: list[str], *, task: str, settings: Settings) -> list[str]:
    model_name = settings.rag_embedding_model.split(":", 1)[0].casefold()
    if model_name == MULTILINGUAL_EMBEDDING_MODEL:
        prefix = f"search_{task}: "
        return [f"{prefix}{text}" for text in texts]
    return texts


def _knowledge_base_path(settings: Settings) -> Path:
    directory = Path(settings.rag_documents_dir)
    if not directory.is_absolute():
        directory = Path(__file__).resolve().parents[2] / directory
    return directory


def _read_document(path: Path) -> list[tuple[int, str]]:
    if path.suffix.lower() == ".pdf":
        try:
            pages = list(PdfReader(str(path)).pages)
            if not pages:
                raise DocumentExtractionError(f"PDF has no pages: {path.name}")

            extracted = []
            empty_pages = []
            for page_number, page in enumerate(pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    extracted.append((page_number, text))
                else:
                    empty_pages.append(page_number)
        except DocumentExtractionError:
            raise
        except (PdfReadError, OSError, EOFError, ValueError) as exc:
            raise DocumentExtractionError(
                f"Unable to read PDF '{path.name}': {exc}"
            ) from exc

        if empty_pages:
            pages_text = ", ".join(map(str, empty_pages))
            raise DocumentExtractionError(
                f"PDF extraction may be incomplete for '{path.name}': "
                f"no selectable text on page(s) {pages_text}; pages may be blank or scanned."
            )
        return extracted

    if path.suffix.lower() == ".docx":
        try:
            document = WordDocument(str(path))
            blocks = []
            for item in document.iter_inner_content():
                if isinstance(item, Paragraph):
                    text = item.text.strip()
                    if not text:
                        continue
                    style_name = item.style.name.casefold() if item.style else ""
                    heading = re.fullmatch(r"(?:heading|titre)\s+([1-6])", style_name)
                    if heading:
                        text = f"{'#' * int(heading[1])} {text}"
                    elif style_name in {"title", "titre"}:
                        text = f"# {text}"
                    elif style_name in {"subtitle", "sous-titre"}:
                        text = f"## {text}"
                    blocks.append(text)
                elif isinstance(item, Table):
                    for row in item.rows:
                        cells = [re.sub(r"\s+", " ", cell.text).strip() for cell in row.cells]
                        if any(cells):
                            blocks.append(" | ".join(cells))
            text = "\n\n".join(blocks)
        except (BadZipFile, PackageNotFoundError, OSError, KeyError, ValueError) as exc:
            raise DocumentExtractionError(
                f"Unable to read DOCX '{path.name}': {exc}"
            ) from exc

        if not text.strip():
            raise DocumentExtractionError(f"No extractable text found in DOCX: {path.name}")
        return [(0, text)]

    return [(0, path.read_text(encoding="utf-8"))]


def _document_chunks(root: Path) -> list[DocumentChunk]:
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.name.casefold() != "readme.md"
        and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not files:
        raise FileNotFoundError(
            f"No PDF, DOCX, Markdown, or text documents found in the knowledge-base folder: {root}"
        )

    chunks: list[DocumentChunk] = []
    for path in files:
        source_path = path.relative_to(root).as_posix()
        file_chunks = []
        for page, text in _read_document(path):
            file_chunks.extend(
                DocumentChunk(
                    source_path=source_path,
                    title=path.stem,
                    page=page,
                    chunk_index=index,
                    content=content,
                )
                for index, content in enumerate(chunk_text(text))
            )
        if not file_chunks:
            raise DocumentExtractionError(
                f"No selectable text could be extracted from document: {path.name}"
            )
        chunks.extend(file_chunks)
    return chunks


def _published_document_chunks(settings: Settings) -> list[DocumentChunk]:
    with psycopg.connect(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT d.id, d.current_version_id, d.title, v.original_filename, v.storage_path
            FROM document_source AS d
            JOIN document_version AS v ON v.id = d.current_version_id
            WHERE d.status = 'active'
              AND d.deleted_at IS NULL
            ORDER BY d.id
            """
        ).fetchall()

    chunks: list[DocumentChunk] = []
    for document_id, version_id, title, filename, storage_path in rows:
        path = resolve_stored_file(storage_path, settings=settings)
        document_chunks = [
            DocumentChunk(
                source_path=storage_path,
                title=title,
                page=page,
                chunk_index=index,
                content=content,
                document_id=document_id,
                document_version_id=version_id,
            )
            for page, text in _read_document(path)
            for index, content in enumerate(chunk_text(text))
        ]
        if not document_chunks:
            raise DocumentExtractionError(
                f"No selectable text could be extracted from document: {filename}"
            )
        chunks.extend(document_chunks)
    return chunks


def _database_url(settings: Settings) -> str:
    return settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".8g") for value in vector) + "]"


def _lexical_terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[^\W_]+", text.casefold()):
        if len(token) <= 2 or token in _RERANK_STOPWORDS:
            continue
        if len(token) > 4 and token.endswith("s"):
            token = token[:-1]
        terms.add(token)
    return terms


def _humanize_source_title(title: str) -> str:
    parts = title.casefold().split("-")
    if len(parts) < 3 or parts[0] not in {"iit", "isb"}:
        return title

    source_type = _SOURCE_TYPE_LABELS.get(parts[-1])
    if source_type is None:
        return title

    program_name = " ".join(
        _SOURCE_WORD_LABELS.get(word, word.capitalize())
        for word in parts[1:-1]
    )
    return f"{source_type} — {program_name} ({parts[0].upper()})"


def _rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    query_terms = _lexical_terms(query)
    if not query_terms:
        return chunks[:top_k]

    def rank_key(chunk: RetrievedChunk) -> tuple[float, float, str, int]:
        title_terms = _lexical_terms(f"{chunk.title} {chunk.origin}")
        chunk_terms = _lexical_terms(chunk.content)
        lexical_coverage = len(query_terms & chunk_terms) / len(query_terms)
        title_coverage = len(query_terms & title_terms) / len(query_terms)
        combined_score = (
            chunk.similarity
            + LEXICAL_RERANK_WEIGHT * lexical_coverage
            + TITLE_RERANK_WEIGHT * title_coverage
        )
        return (
            -combined_score,
            -chunk.similarity,
            chunk.origin,
            chunk.page or 0,
        )

    return sorted(chunks, key=rank_key)[:top_k]


def _initialize_schema(settings: Settings, embedding_dimensions: int) -> None:
    if not 1 <= embedding_dimensions <= 16000:
        raise ValueError("Embedding dimensions must be between 1 and 16000.")

    with psycopg.connect(_database_url(settings)) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                source_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                title TEXT NOT NULL,
                page INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding vector({embedding_dimensions}) NOT NULL,
                document_id UUID,
                document_version_id UUID,
                UNIQUE (source_path, page, chunk_index)
            )
            """
        )
        connection.execute(
            "ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS embedding_model TEXT"
        )
        connection.execute(
            "ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS document_id UUID"
        )
        connection.execute(
            "ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS document_version_id UUID"
        )
        embedding_type = connection.execute(
            """
            SELECT format_type(attribute.atttypid, attribute.atttypmod)
            FROM pg_attribute AS attribute
            WHERE attribute.attrelid = 'public.rag_chunks'::regclass
              AND attribute.attname = 'embedding'
              AND NOT attribute.attisdropped
            """
        ).fetchone()[0]
        expected_type = f"vector({embedding_dimensions})"
        if embedding_type == "vector":
            connection.execute(
                f"""
                ALTER TABLE rag_chunks
                ALTER COLUMN embedding TYPE {expected_type}
                USING embedding::{expected_type}
                """
            )
        elif embedding_type != expected_type:
            raise ValueError(
                f"rag_chunks uses {embedding_type}, but the configured embedding model "
                f"produces {expected_type}. Rebuild the RAG index before changing embedding models."
            )
        if embedding_dimensions <= 2000:
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx
                ON rag_chunks USING hnsw (embedding vector_cosine_ops)
                """
            )


def _store_document_chunks(
    source_path: str,
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
    settings: Settings,
) -> None:
    with psycopg.connect(_database_url(settings)) as connection:
        with connection.transaction():
            connection.execute("DELETE FROM rag_chunks WHERE source_path = %s", (source_path,))
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO rag_chunks
                        (source_id, source_path, title, page, chunk_index, content, embedding_model,
                         embedding, document_id, document_version_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
                    """,
                    [
                        (
                            hashlib.sha256(
                                f"{chunk.source_path}:{chunk.page}:{chunk.chunk_index}".encode("utf-8")
                            ).hexdigest(),
                            chunk.source_path,
                            chunk.title,
                            chunk.page,
                            chunk.chunk_index,
                            chunk.content,
                            settings.rag_embedding_model,
                            _vector_literal(embedding),
                            chunk.document_id,
                            chunk.document_version_id,
                        )
                        for chunk, embedding in zip(chunks, embeddings, strict=True)
                    ],
                )


async def ingest_documents(*, settings: Settings | None = None) -> int:
    config = settings or get_settings()
    root = _knowledge_base_path(config)
    if not root.is_dir():
        raise FileNotFoundError(f"Knowledge-base folder does not exist: {root}")
    chunks = _document_chunks(root)
    chunks.extend(await asyncio.to_thread(_published_document_chunks, config))

    grouped: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.source_path, []).append(chunk)

    stored_count = 0
    embedding_dimensions: int | None = None
    for source_path, document_chunks in grouped.items():
        document_embeddings = []
        for start in range(0, len(document_chunks), EMBEDDING_BATCH_SIZE):
            batch = document_chunks[start:start + EMBEDDING_BATCH_SIZE]
            embeddings = await embed_texts(
                _embedding_inputs(
                    [chunk.content for chunk in batch],
                    task="document",
                    settings=config,
                ),
                settings=config,
            )
            if len(embeddings) != len(batch):
                raise AIUnavailableError("Le nombre de vecteurs ne correspond pas au nombre de passages.")
            batch_dimensions = {len(embedding) for embedding in embeddings}
            if len(batch_dimensions) != 1:
                raise AIUnavailableError("Le modèle a renvoyé des vecteurs de dimensions différentes.")
            current_dimensions = batch_dimensions.pop()
            if embedding_dimensions is None:
                embedding_dimensions = current_dimensions
                await asyncio.to_thread(_initialize_schema, config, embedding_dimensions)
            elif current_dimensions != embedding_dimensions:
                raise AIUnavailableError("La dimension des vecteurs a changé pendant l'ingestion.")
            document_embeddings.extend(embeddings)
        await asyncio.to_thread(
            _store_document_chunks,
            source_path,
            document_chunks,
            document_embeddings,
            config,
        )
        stored_count += len(document_chunks)
    return stored_count


def _search(
    vector: list[float],
    query: str,
    top_k: int,
    min_similarity: float,
    settings: Settings,
) -> list[RetrievedChunk]:
    literal = _vector_literal(vector)
    candidate_limit = min(
        max(top_k * RERANK_CANDIDATE_MULTIPLIER, MIN_RERANK_CANDIDATES),
        MAX_RERANK_CANDIDATES,
    )
    with psycopg.connect(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT chunk.source_id, chunk.title,
                   COALESCE(version.original_filename, chunk.source_path) AS origin,
                   chunk.page, chunk.content,
                   1 - (chunk.embedding <=> %s::vector) AS similarity
            FROM rag_chunks AS chunk
            LEFT JOIN document_version AS version ON version.id = chunk.document_version_id
            WHERE chunk.embedding_model = %s
              AND (
                  chunk.document_id IS NULL
                  OR EXISTS (
                      SELECT 1
                      FROM document_source AS document
                      WHERE document.id = chunk.document_id
                        AND document.status = 'active'
                        AND document.deleted_at IS NULL
                        AND document.current_version_id = chunk.document_version_id
                  )
              )
              AND 1 - (chunk.embedding <=> %s::vector) >= %s
            ORDER BY chunk.embedding <=> %s::vector
            LIMIT %s
            """,
            (
                literal,
                settings.rag_embedding_model,
                literal,
                min_similarity,
                literal,
                candidate_limit,
            ),
        ).fetchall()
    candidates = [
        RetrievedChunk(
            source_id=row[0],
            title=_humanize_source_title(row[1]),
            origin=row[2],
            page=row[3] or None,
            content=row[4],
            similarity=float(row[5]),
        )
        for row in rows
    ]
    return _rerank_chunks(query, candidates, top_k)


async def retrieve(
    query: str,
    *,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    config = settings or get_settings()
    embeddings = await embed_texts(
        _embedding_inputs([query], task="query", settings=config),
        settings=config,
    )
    try:
        return await asyncio.to_thread(
            _search,
            embeddings[0],
            query,
            config.rag_top_k,
            config.rag_min_similarity,
            config,
        )
    except psycopg.Error as exc:
        raise AIUnavailableError(
            "La base RAG n'est pas disponible ou initialisée. Démarrez PostgreSQL et ingérez les documents officiels."
        ) from exc
