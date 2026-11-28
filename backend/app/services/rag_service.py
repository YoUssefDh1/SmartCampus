import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg

from app.core.config import Settings, get_settings
from app.core.errors import AIUnavailableError
from app.services.embedding_service import embed_texts

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 180
EMBEDDING_BATCH_SIZE = 16
RERANK_CANDIDATE_MULTIPLIER = 5
MIN_RERANK_CANDIDATES = 20
MAX_RERANK_CANDIDATES = 100
LEXICAL_RERANK_WEIGHT = 0.1
TITLE_RERANK_WEIGHT = 0.25
SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt"}
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


def chunk_text(text: str, *, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size must be positive and overlap must be smaller than size.")
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []

    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = end - overlap
    return chunks


def _knowledge_base_path(settings: Settings) -> Path:
    directory = Path(settings.rag_documents_dir)
    if not directory.is_absolute():
        directory = Path(__file__).resolve().parents[2] / directory
    return directory


def _read_document(path: Path) -> list[tuple[int, str]]:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return [
            (page_number, page.extract_text() or "")
            for page_number, page in enumerate(reader.pages, start=1)
        ]
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
            f"No PDF, Markdown, or text documents found in the knowledge-base folder: {root}"
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
            raise ValueError(f"No selectable text could be extracted from document: {path}")
        chunks.extend(file_chunks)
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
                UNIQUE (source_path, page, chunk_index)
            )
            """
        )
        connection.execute(
            "ALTER TABLE rag_chunks ADD COLUMN IF NOT EXISTS embedding_model TEXT"
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
                        (source_id, source_path, title, page, chunk_index, content, embedding_model, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
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
                [chunk.content for chunk in batch],
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
            SELECT source_id, title, source_path, page, content,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM rag_chunks
            WHERE embedding_model = %s
              AND 1 - (embedding <=> %s::vector) >= %s
            ORDER BY embedding <=> %s::vector
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
    embeddings = await embed_texts([query], settings=config)
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
