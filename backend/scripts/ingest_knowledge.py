#!/usr/bin/env python3
"""Embed official SmartCampus source files and store them in PostgreSQL/pgvector."""

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.services.rag_service import ingest_documents  # noqa: E402


async def run(documents_dir: str | None) -> None:
    settings = get_settings()
    if documents_dir:
        settings = settings.model_copy(update={"rag_documents_dir": documents_dir})
    try:
        count = await ingest_documents(settings=settings)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Ingested {count} chunks from {settings.rag_documents_dir}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--documents-dir",
        help="Override RAG_DOCUMENTS_DIR (relative to backend or absolute path).",
    )
    args = parser.parse_args()
    asyncio.run(run(args.documents_dir))
