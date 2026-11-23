"""Assemble tous les routeurs de l'API v1 et documente les erreurs communes dans Swagger."""
from fastapi import APIRouter

from app.api.v1.endpoints import (admin, appointments, auth, candidates, catalog, catalog_pricing, chat,
                                  documents, health, preregistrations, programs, qcm, stats)
from app.schemas.common import ErrorResponse

COMMON_ERRORS = {
    401: {"model": ErrorResponse, "description": "Jeton absent, invalide ou expiré"},
    403: {"model": ErrorResponse, "description": "Rôle non autorisé ou ressource d'un autre utilisateur"},
    422: {"model": ErrorResponse, "description": "Données invalides"},
    500: {"model": ErrorResponse, "description": "Erreur interne du serveur"},
}

api_router = APIRouter(responses=COMMON_ERRORS)
for module in (health, auth, programs, catalog, catalog_pricing, candidates, chat, documents, preregistrations, qcm,
               appointments, stats, admin):
    api_router.include_router(module.router)
