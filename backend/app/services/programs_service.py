"""Catalogue PUBLIC (candidats, visiteurs, agent IA) - source : PostgreSQL (SA-20).

Règle : seules les formations actives et les informations officielles (publiées et valides
aujourd'hui, vues v_official_*) sont renvoyées. Les brouillons ne sortent jamais d'ici.

Pour l'agent IA (Membre 5) : appeler get_program_detail(conn, program_id) ou les fonctions
official_* de tuition_admission_service ; ne jamais lire directement les tables tuition_fee,
admission_requirement ou payment_plan.
"""
from uuid import UUID

import psycopg

from app.core.errors import NotFoundError
from app.schemas.common import Page
from app.schemas.program import (CurriculumPublic, Program, ProgramAdmission, ProgramCurriculum, ProgramDetail,
                                 ProgramTuition, SpecialtyPublic)
from app.services import catalog_service, tuition_admission_service
from app.services.db_utils import fetch_page

PUBLIC_SELECT = catalog_service.PROGRAM_SELECT + """,
       (SELECT min(v.amount) FROM v_official_tuition_fee v
         WHERE v.program_id = p.id AND v.fee_type = 'tuition') AS tuition_from,
       (SELECT min(v.currency) FROM v_official_tuition_fee v
         WHERE v.program_id = p.id AND v.fee_type = 'tuition') AS tuition_currency"""


def list_programs(conn: psycopg.Connection, *, q: str | None = None, school: str | None = None,
                  level: str | None = None, cycle: str | None = None, language: str | None = None,
                  sort: str = "school", page: int = 1, size: int = 20) -> Page[Program]:
    w = catalog_service.program_filters(q, school, level, cycle, language, is_active=True)
    order = catalog_service.PROGRAM_SORTS.get(sort, "i.code, p.name")
    rows, total = fetch_page(conn, PUBLIC_SELECT, catalog_service.PROGRAM_FROM, w, order, page, size)
    return Page[Program](items=[Program(**r) for r in rows], total=total, page=page, size=size)


def _active_program(conn: psycopg.Connection, program_id: UUID) -> dict:
    row = conn.execute(f"{PUBLIC_SELECT}{catalog_service.PROGRAM_FROM} WHERE p.id = %s AND p.is_active",
                       (program_id,)).fetchone()
    if not row:
        raise NotFoundError("Formation introuvable.")
    return row


def get_program(conn: psycopg.Connection, program_id: UUID) -> Program:
    return Program(**_active_program(conn, program_id))


def get_program_detail(conn: psycopg.Connection, program_id: UUID) -> ProgramDetail:
    row = _active_program(conn, program_id)
    specialties = conn.execute("SELECT id, name, description FROM specialty WHERE program_id = %s AND is_active "
                               "ORDER BY name", (program_id,)).fetchall()
    return ProgramDetail(
        **row,
        specialties=[SpecialtyPublic(**s) for s in specialties],
        admission_requirements=tuition_admission_service.official_admission_requirements(conn, program_id),
        tuition_fees=tuition_admission_service.official_tuition_fees(conn, program_id),
        payment_plans=tuition_admission_service.official_payment_plans(conn, program_id),
    )


def get_tuition(conn: psycopg.Connection, program_id: UUID, academic_year: str | None = None) -> ProgramTuition:
    row = _active_program(conn, program_id)
    return ProgramTuition(
        program_id=program_id, program_name=row["name"], school=row["school"], academic_year=academic_year,
        fees=tuition_admission_service.official_tuition_fees(conn, program_id, academic_year),
        payment_plans=tuition_admission_service.official_payment_plans(conn, program_id, academic_year),
    )


def get_admission(conn: psycopg.Connection, program_id: UUID, academic_year: str | None = None) -> ProgramAdmission:
    row = _active_program(conn, program_id)
    return ProgramAdmission(
        program_id=program_id, program_name=row["name"], school=row["school"], academic_year=academic_year,
        requirements=tuition_admission_service.official_admission_requirements(conn, program_id, academic_year),
    )


def get_curriculum(conn: psycopg.Connection, program_id: UUID, academic_year: str | None = None) -> ProgramCurriculum:
    row = _active_program(conn, program_id)
    page = catalog_service.list_curricula(conn, None, program_id=program_id, academic_year=academic_year,
                                          is_active=True, size=100)
    subjects = catalog_service.curriculum_subjects(conn, [c.id for c in page.items])
    return ProgramCurriculum(
        program_id=program_id, program_name=row["name"], school=row["school"],
        curricula=[CurriculumPublic(**c.model_dump(), subjects=subjects[c.id]) for c in page.items],
    )
