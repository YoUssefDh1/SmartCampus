"""Gestion centralisée des erreurs (format défini en SA-5).

Toutes les erreurs de l'API ont la forme :
{"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("smartcampus")


class AppError(Exception):
    """Erreur métier : à lever depuis les services et les routes."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str = "Requête invalide.", details: list | None = None):
        self.message = message
        self.details = details or []
        super().__init__(message)


class UnauthorizedError(AppError):
    status_code, code = 401, "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code, code = 403, "FORBIDDEN"


class NotFoundError(AppError):
    status_code, code = 404, "NOT_FOUND"


class ConflictError(AppError):
    status_code, code = 409, "CONFLICT"


class FileTooLargeError(AppError):
    status_code, code = 413, "FILE_TOO_LARGE"


class UnsupportedMediaTypeError(AppError):
    status_code, code = 415, "UNSUPPORTED_MEDIA_TYPE"


class TooManyRequestsError(AppError):
    status_code, code = 429, "TOO_MANY_REQUESTS"


class AIUnavailableError(AppError):
    status_code, code = 503, "AI_UNAVAILABLE"


class NotImplementedYetError(AppError):
    """Route prévue dans le contrat d'API mais pas encore codée."""

    status_code, code = 501, "NOT_IMPLEMENTED"


_HTTP_CODES = {
    400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED", 409: "CONFLICT", 413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE", 422: "VALIDATION_ERROR", 429: "TOO_MANY_REQUESTS",
}


def _body(request: Request, code: str, message: str, details: list | None = None) -> dict:
    return {"error": {
        "code": code,
        "message": message,
        "details": details or [],
        "request_id": getattr(request.state, "request_id", None),
    }}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_body(request, exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"] if p != "body"), "issue": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content=_body(request, "VALIDATION_ERROR", "Données invalides.", details))

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_body(request, code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, exc: Exception):
        logger.exception("Erreur inattendue (request_id=%s)", getattr(request.state, "request_id", None))
        return JSONResponse(status_code=500, content=_body(request, "INTERNAL_ERROR", "Erreur interne du serveur."))
