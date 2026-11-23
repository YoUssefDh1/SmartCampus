import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import AIUnavailableError
from app.services.llm_service import generate_reply


@pytest.mark.parametrize(
    ("model", "expect_thinking_disabled"),
    [("qwen3:8b", True), ("gemma3:4b", False)],
)
def test_generate_reply_uses_configured_ollama_model_and_options(model, expect_thinking_disabled):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.read())
        return httpx.Response(200, json={"message": {"content": "Bonjour"}})

    settings = Settings(
        llm_base_url="http://localhost:11434/",
        llm_model=model,
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
    assert captured["payload"]["model"] == model
    assert captured["payload"]["options"]["num_predict"] == 300
    assert ("think" in captured["payload"]) is expect_thinking_disabled
    if expect_thinking_disabled:
        assert captured["payload"]["think"] is False


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
