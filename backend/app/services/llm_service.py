import json

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AIUnavailableError


async def generate_reply(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    config = settings or get_settings()
    url = f"{config.llm_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": config.llm_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": config.llm_temperature,
            "num_predict": config.llm_max_tokens,
        },
    }

    try:
        async with httpx.AsyncClient(
            timeout=config.llm_timeout_seconds,
            transport=transport,
        ) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise AIUnavailableError(
            "Le service IA est indisponible. Vérifiez qu'Ollama fonctionne et que le modèle configuré est installé."
        ) from exc
    except json.JSONDecodeError as exc:
        raise AIUnavailableError("Le service IA a renvoyé une réponse invalide.") from exc

    try:
        reply = data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise AIUnavailableError("Le service IA a renvoyé une réponse invalide.") from exc

    if not isinstance(reply, str) or not reply.strip():
        raise AIUnavailableError("Le service IA a renvoyé une réponse vide.")
    return reply.strip()
