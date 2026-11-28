import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AIUnavailableError
from app.services.embedding_service import embed_texts


def test_embed_texts_uses_configured_embedding_model():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read()
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    result = asyncio.run(embed_texts(
        ["first", "second"],
        settings=Settings(
            llm_base_url="http://localhost:11434/",
            rag_embedding_model="nomic-embed-text-v2-moe",
        ),
        transport=httpx.MockTransport(handler),
    ))

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "http://localhost:11434/api/embed"
    assert b'"model":"nomic-embed-text-v2-moe"' in captured["body"]


def test_embed_texts_reports_incomplete_vectors():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": []})

    with pytest.raises(AIUnavailableError):
        asyncio.run(embed_texts(
            ["text"],
            transport=httpx.MockTransport(handler),
        ))
