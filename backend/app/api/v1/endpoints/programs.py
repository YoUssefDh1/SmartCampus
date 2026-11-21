"""Routes « Catalogue » (Membre 3). Liste et détail : démo. Tarifs / admission : à coder."""
from fastapi import APIRouter, Query

from app.core.errors import NotFoundError, NotImplementedYetError
from app.schemas.common import ErrorResponse, Page
from app.schemas.program import Program
from app.services import programs_service

router = APIRouter(prefix="/programs", tags=["Catalogue"])


@router.get("", response_model=Page[Program], summary="Liste des formations")
def list_programs(school: str | None = Query(None, description="IIT ou ISB"),
                  level: str | None = Query(None, description="Licence, Préparatoire, Ingénierie"),
                  page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
    return programs_service.list_programs(school, level, page, size)


@router.get("/{program_id}", response_model=Program, summary="Détail d'une formation",
            responses={404: {"model": ErrorResponse, "description": "Formation introuvable"}})
def get_program(program_id: str):
    return programs_service.get_program(program_id)


@router.get("/{program_id}/tuition", summary="Tarifs")
def get_tuition(program_id: str):
    # TODO (Membre 3, SA-21)
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")


@router.get("/{program_id}/admission", summary="Conditions d'admission")
def get_admission(program_id: str):
    # TODO (Membre 3, SA-21)
    raise NotImplementedYetError("Route prévue mais pas encore implémentée.")
