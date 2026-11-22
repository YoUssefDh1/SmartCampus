import asyncio

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AIUnavailableError
from app.services.llm_service import generate_reply


def test_generate_reply_uses_configured_ollama_model_and_options():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = request.read()
        return httpx.Response(200, json={"message": {"content": "Bonjour"}})

    settings = Settings(
        llm_base_url="http://localhost:11434/",
        llm_model="qwen3:8b",
        llm_temperature=0.1,
        llm_max_tokens=300,
    )
    result = asyncio.run(generate_reply(
        [{"role": "user", "content": "Salut"}],
        settings=settings,
        transport=httpx.MockTransport(handler),
    ))

    assert result == "Bonjour"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert b'"model":"qwen3:8b"' in captured["payload"]
    assert b'"num_predict":300' in captured["payload"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"error": "model not found"}),
        httpx.Response(200, json={"unexpected": "shape"}),
        httpx.Response(200, json={"message": {"content": "  "}}),
    ],
)
def test_generate_reply_surfaces_invalid_or_unavailable_model_responses(response):
    def handler(_request: httpx.Request) -> httpx.Response:
        return response

    with pytest.raises(AIUnavailableError):
        asyncio.run(generate_reply(
            [{"role": "user", "content": "Salut"}],
            transport=httpx.MockTransport(handler),
        ))


def test_generate_reply_surfaces_connection_errors():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama is not running")

    with pytest.raises(AIUnavailableError):
        asyncio.run(generate_reply(
            [{"role": "user", "content": "Salut"}],
            transport=httpx.MockTransport(handler),
        ))
