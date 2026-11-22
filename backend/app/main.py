import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import RequestIdMiddleware
from app.db.session import close_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TAGS = [
    {"name": "Système", "description": "Santé du service"},
    {"name": "Auth", "description": "Sessions visiteur, comptes, connexion"},
    {"name": "Catalogue", "description": "Consultation publique : formations IIT / ISB, tarifs et conditions "
                                         "d'admission officiels (publiés et valides)"},
    {"name": "Gestion des formations", "description": "Responsables / admin : formations, spécialités, "
                                                      "programmes pédagogiques, matières"},
    {"name": "Tarifs et admission", "description": "Responsables / admin : frais de scolarité, modalités de "
                                                   "paiement, conditions d'admission, publication et validité"},
    {"name": "Candidats", "description": "Dossier et profil d'orientation"},
    {"name": "Conversations", "description": "Chat texte et vocal, historique"},
    {"name": "Documents", "description": "Pièces des candidats"},
    {"name": "Préinscriptions", "description": "Création et suivi des préinscriptions"},
    {"name": "QCM", "description": "QCM ciblé avant l'entretien"},
    {"name": "Rendez-vous", "description": "Planification des entretiens"},
    {"name": "Statistiques", "description": "Tableaux de bord (direction, admin)"},
    {"name": "Administration", "description": "Comptes, rôles, journaux"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_pool()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version=s.app_version,
        description="API de la plateforme agentique d'orientation universitaire (IIT / ISB).",
        openapi_tags=TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)
    app.include_router(api_router, prefix=s.api_prefix)
    return app


app = create_app()
