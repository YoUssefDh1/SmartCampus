import json

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import AIUnavailableError


async def embed_texts(
    texts: list[str],
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[list[float]]:
    if not texts:
        return []

    config = settings or get_settings()
    url = f"{config.llm_base_url.rstrip('/')}/api/embed"
    payload = {
        "model": config.rag_embedding_model,
        "input": texts,
        "truncate": False,
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
            "Le modèle d'embeddings Ollama est indisponible. Vérifiez Ollama et RAG_EMBEDDING_MODEL."
        ) from exc
    except json.JSONDecodeError as exc:
        raise AIUnavailableError("Le service d'embeddings a renvoyé une réponse invalide.") from exc

    embeddings = data.get("embeddings") if isinstance(data, dict) else None
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise AIUnavailableError("Le service d'embeddings a renvoyé un résultat incomplet.")

    vectors: list[list[float]] = []
    for embedding in embeddings:
        if not isinstance(embedding, list) or not embedding:
            raise AIUnavailableError("Le service d'embeddings a renvoyé un vecteur invalide.")
        if any(not isinstance(value, (int, float)) for value in embedding):
            raise AIUnavailableError("Le service d'embeddings a renvoyé un vecteur invalide.")
        vectors.append([float(value) for value in embedding])
    return vectors
