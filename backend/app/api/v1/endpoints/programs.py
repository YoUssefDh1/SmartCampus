"""Routes « Catalogue » publiques (Membre 3) : candidats, visiteurs et agent IA.

Aucune authentification. Ne renvoient que les formations actives et les informations officielles
(publiées et valides aujourd'hui). La gestion se fait dans /catalog (catalog.py, catalog_pricing.py).
"""
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query

from app.db.session import get_db
from app.schemas.catalog import AcademicYear, Cycle
from app.schemas.common import ErrorResponse, Page
from app.schemas.program import Program, ProgramAdmission, ProgramCurriculum, ProgramDetail, ProgramTuition
from app.services import programs_service

router = APIRouter(prefix="/programs", tags=["Catalogue"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Formation introuvable ou inactive"}}


@router.get("", response_model=Page[Program], summary="Liste des formations (recherche et filtres)")
def list_programs(
    q: str | None = Query(None, description="Recherche dans le nom, le code, la description, les débouchés"),
    school: str | None = Query(None, description="IIT ou ISB"),
    level: str | None = Query(None, description="Préparatoire, Ingénierie, Licence, Master (ou code du cycle)"),
    cycle: Cycle | None = Query(None, description="Code du cycle"),
    language: str | None = Query(None, description="Langue d'enseignement : fr, en, ar"),
    sort: Literal["school", "name", "-name", "duration", "-created_at"] = "school",
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
    conn: psycopg.Connection = Depends(get_db),
):
    return programs_service.list_programs(conn, q=q, school=school, level=level, cycle=cycle, language=language,
                                          sort=sort, page=page, size=size)


@router.get("/{program_id}", response_model=ProgramDetail, responses=NOT_FOUND,
            summary="Fiche formation : spécialités, admission, frais et modalités officiels")
def get_program(program_id: UUID, conn: psycopg.Connection = Depends(get_db)):
    return programs_service.get_program_detail(conn, program_id)


@router.get("/{program_id}/tuition", response_model=ProgramTuition, responses=NOT_FOUND,
            summary="Frais de scolarité et modalités de paiement officiels en vigueur")
def get_tuition(program_id: UUID, academic_year: AcademicYear | None = Query(None, examples=["2026-2027"]),
                conn: psycopg.Connection = Depends(get_db)):
    return programs_service.get_tuition(conn, program_id, academic_year)


@router.get("/{program_id}/admission", response_model=ProgramAdmission, responses=NOT_FOUND,
            summary="Conditions d'admission et prérequis officiels en vigueur")
def get_admission(program_id: UUID, academic_year: AcademicYear | None = Query(None, examples=["2026-2027"]),
                  conn: psycopg.Connection = Depends(get_db)):
    return programs_service.get_admission(conn, program_id, academic_year)


@router.get("/{program_id}/curriculum", response_model=ProgramCurriculum, responses=NOT_FOUND,
            summary="Programmes pédagogiques actifs et leurs matières")
def get_curriculum(program_id: UUID, academic_year: AcademicYear | None = Query(None, examples=["2026-2027"]),
                   conn: psycopg.Connection = Depends(get_db)):
    return programs_service.get_curriculum(conn, program_id, academic_year)
