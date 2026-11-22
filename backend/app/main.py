import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import RequestIdMiddleware
from app.services.guest_service import purge_expired_guest_conversations

logger = logging.getLogger("smartcampus")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

TAGS = [
    {"name": "Système", "description": "Santé du service"},
    {"name": "Auth", "description": "Sessions visiteur, comptes, connexion"},
    {"name": "Catalogue", "description": "Formations IIT / ISB, tarifs, conditions d'admission"},
    {"name": "Candidats", "description": "Dossier et profil d'orientation"},
    {"name": "Conversations", "description": "Chat texte et vocal, historique"},
    {"name": "Documents", "description": "Pièces des candidats"},
    {"name": "Préinscriptions", "description": "Création et suivi des préinscriptions"},
    {"name": "QCM", "description": "QCM ciblé avant l'entretien"},
    {"name": "Rendez-vous", "description": "Planification des entretiens"},
    {"name": "Statistiques", "description": "Tableaux de bord (direction, admin)"},
    {"name": "Administration", "description": "Comptes, rôles, journaux"},
]


async def _guest_purge_loop(interval_minutes: int) -> None:
    """Purge périodique des conversations invitées expirées (SA-25)."""
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            deleted = await asyncio.to_thread(purge_expired_guest_conversations)
            if deleted:
                logger.info("Purge visiteur : %s conversation(s) expirée(s) supprimée(s).", deleted)
        except Exception:
            logger.exception("Échec de la purge des sessions visiteur.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    purge_task = None
    if s.environment != "test":
        purge_task = asyncio.create_task(_guest_purge_loop(s.guest_purge_interval_minutes))
    yield
    if purge_task:
        purge_task.cancel()


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
