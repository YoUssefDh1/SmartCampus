"""Identifiant de requête : ajouté à chaque réponse et à chaque erreur pour faciliter le débogage."""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:8]}"
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
