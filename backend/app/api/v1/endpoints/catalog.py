"""Routes « Gestion des formations » (Membre 3) : responsables académiques et administrateur.

Formations, spécialités, programmes pédagogiques, matières : ajouter, consulter, modifier,
supprimer, rechercher, filtrer. Un responsable IIT/ISB ne voit et ne modifie que son école.
"""
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, Response

from app.core.security import CATALOG_READ_ROLES, CATALOG_WRITE_ROLES, Actor, require_roles
from app.db.session import get_db
from app.schemas.catalog import (AcademicYear, Cycle, CurriculumCreate, CurriculumDetail, CurriculumDuplicate,
                                 CurriculumOut, CurriculumSubjectCreate, CurriculumSubjectUpdate, CurriculumUpdate,
                                 InstitutionOut, ProgramCreate, ProgramOut, ProgramUpdate, SpecialtyCreate,
                                 SpecialtyOut, SpecialtyUpdate, SubjectCreate, SubjectOut, SubjectUpdate)
from app.schemas.common import ErrorResponse, Page
from app.services import catalog_service as svc

router = APIRouter(prefix="/catalog", tags=["Gestion des formations"])

reader = require_roles(*CATALOG_READ_ROLES)
writer = require_roles(*CATALOG_WRITE_ROLES)
ERRORS = {
    404: {"model": ErrorResponse, "description": "Élément introuvable"},
    409: {"model": ErrorResponse, "description": "Doublon, ou suppression d'un élément encore utilisé"},
}
Page_ = Query(1, ge=1)
Size = Query(20, ge=1, le=100)


def _no_content() -> Response:
    return Response(status_code=204)


# --- Écoles -------------------------------------------------------------------
@router.get("/institutions", response_model=list[InstitutionOut], summary="Écoles (listes déroulantes)")
def list_institutions(_: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.list_institutions(conn)


# --- Formations -----------------------------------------------------------------
@router.get("/programs", response_model=Page[ProgramOut], summary="Rechercher et filtrer les formations")
def list_programs(
    q: str | None = Query(None, description="Nom, code, description, diplôme, débouchés"),
    school: str | None = Query(None, description="IIT ou ISB (admin / direction)"),
    cycle: Cycle | None = None,
    level: str | None = Query(None, description="Libellé du cycle : Préparatoire, Ingénierie..."),
    language: str | None = Query(None, description="fr, en, ar"),
    is_active: bool | None = Query(None, description="Vide = actives et inactives"),
    sort: Literal["name", "-name", "code", "-code", "school", "duration", "created_at", "-created_at",
                  "updated_at", "-updated_at"] = "name",
    page: int = Page_, size: int = Size,
    actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db),
):
    return svc.list_programs(conn, actor, q=q, school=school, cycle=cycle, level=level, language=language,
                             is_active=is_active, sort=sort, page=page, size=size)


@router.post("/programs", response_model=ProgramOut, status_code=201, responses=ERRORS,
             summary="Ajouter une formation")
def create_program(body: ProgramCreate, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    return svc.create_program(conn, actor, body)


@router.get("/programs/{program_id}", response_model=ProgramOut, responses=ERRORS, summary="Consulter une formation")
def get_program(program_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_program(conn, program_id, actor)


@router.patch("/programs/{program_id}", response_model=ProgramOut, responses=ERRORS,
              summary="Modifier une formation (désactiver : is_active=false)")
def update_program(program_id: UUID, body: ProgramUpdate, actor: Actor = Depends(writer),
                   conn: psycopg.Connection = Depends(get_db)):
    return svc.update_program(conn, actor, program_id, body)


@router.delete("/programs/{program_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Supprimer une formation (et ses spécialités, programmes, tarifs, conditions)")
def delete_program(program_id: UUID, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    svc.delete_program(conn, actor, program_id)
    return _no_content()


# --- Spécialités ------------------------------------------------------------------
@router.get("/programs/{program_id}/specialties", response_model=Page[SpecialtyOut], responses=ERRORS,
            summary="Spécialités d'une formation")
def list_program_specialties(program_id: UUID, is_active: bool | None = None, page: int = Page_,
                             size: int = Query(50, ge=1, le=100), actor: Actor = Depends(reader),
                             conn: psycopg.Connection = Depends(get_db)):
    return svc.list_specialties(conn, actor, program_id=program_id, is_active=is_active, page=page, size=size)


@router.post("/programs/{program_id}/specialties", response_model=SpecialtyOut, status_code=201, responses=ERRORS,
             summary="Ajouter une spécialité")
def create_specialty(program_id: UUID, body: SpecialtyCreate, actor: Actor = Depends(writer),
                     conn: psycopg.Connection = Depends(get_db)):
    return svc.create_specialty(conn, actor, program_id, body)


@router.get("/specialties", response_model=Page[SpecialtyOut], summary="Rechercher les spécialités")
def list_specialties(q: str | None = None, program_id: UUID | None = None, school: str | None = None,
                     is_active: bool | None = None, page: int = Page_, size: int = Size,
                     actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.list_specialties(conn, actor, program_id=program_id, q=q, school=school, is_active=is_active,
                                page=page, size=size)


@router.get("/specialties/{specialty_id}", response_model=SpecialtyOut, responses=ERRORS,
            summary="Consulter une spécialité")
def get_specialty(specialty_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_specialty(conn, specialty_id, actor)


@router.patch("/specialties/{specialty_id}", response_model=SpecialtyOut, responses=ERRORS,
              summary="Modifier une spécialité")
def update_specialty(specialty_id: UUID, body: SpecialtyUpdate, actor: Actor = Depends(writer),
                     conn: psycopg.Connection = Depends(get_db)):
    return svc.update_specialty(conn, actor, specialty_id, body)


@router.delete("/specialties/{specialty_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Supprimer une spécialité")
def delete_specialty(specialty_id: UUID, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    svc.delete_specialty(conn, actor, specialty_id)
    return _no_content()


# --- Matières ----------------------------------------------------------------------
@router.get("/subjects", response_model=Page[SubjectOut], summary="Rechercher les matières")
def list_subjects(q: str | None = Query(None, description="Code, nom, description"),
                  program_id: UUID | None = Query(None, description="Matières utilisées par cette formation"),
                  curriculum_id: UUID | None = Query(None, description="Matières d'un programme pédagogique"),
                  sort: Literal["code", "name", "-name", "-created_at"] = "code",
                  page: int = Page_, size: int = Query(50, ge=1, le=100),
                  _: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.list_subjects(conn, q=q, program_id=program_id, curriculum_id=curriculum_id, sort=sort,
                             page=page, size=size)


@router.post("/subjects", response_model=SubjectOut, status_code=201, responses=ERRORS, summary="Ajouter une matière")
def create_subject(body: SubjectCreate, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    return svc.create_subject(conn, actor, body)


@router.get("/subjects/{subject_id}", response_model=SubjectOut, responses=ERRORS, summary="Consulter une matière")
def get_subject(subject_id: UUID, _: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_subject(conn, subject_id)


@router.patch("/subjects/{subject_id}", response_model=SubjectOut, responses=ERRORS, summary="Modifier une matière")
def update_subject(subject_id: UUID, body: SubjectUpdate, actor: Actor = Depends(writer),
                   conn: psycopg.Connection = Depends(get_db)):
    return svc.update_subject(conn, actor, subject_id, body)


@router.delete("/subjects/{subject_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Supprimer une matière (refusé si elle est utilisée)")
def delete_subject(subject_id: UUID, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    svc.delete_subject(conn, actor, subject_id)
    return _no_content()


# --- Programmes pédagogiques ------------------------------------------------------------
@router.get("/curricula", response_model=Page[CurriculumOut], summary="Rechercher les programmes pédagogiques")
def list_curricula(program_id: UUID | None = None, specialty_id: UUID | None = None,
                   academic_year: AcademicYear | None = None, is_active: bool | None = None,
                   school: str | None = None, q: str | None = None, page: int = Page_, size: int = Size,
                   actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.list_curricula(conn, actor, program_id=program_id, specialty_id=specialty_id,
                              academic_year=academic_year, is_active=is_active, school=school, q=q,
                              page=page, size=size)


@router.post("/curricula", response_model=CurriculumDetail, status_code=201, responses=ERRORS,
             summary="Ajouter un programme pédagogique")
def create_curriculum(body: CurriculumCreate, actor: Actor = Depends(writer),
                      conn: psycopg.Connection = Depends(get_db)):
    return svc.create_curriculum(conn, actor, body)


@router.get("/curricula/{curriculum_id}", response_model=CurriculumDetail, responses=ERRORS,
            summary="Consulter un programme et ses matières")
def get_curriculum(curriculum_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_curriculum(conn, curriculum_id, actor)


@router.patch("/curricula/{curriculum_id}", response_model=CurriculumDetail, responses=ERRORS,
              summary="Modifier un programme pédagogique")
def update_curriculum(curriculum_id: UUID, body: CurriculumUpdate, actor: Actor = Depends(writer),
                      conn: psycopg.Connection = Depends(get_db)):
    return svc.update_curriculum(conn, actor, curriculum_id, body)


@router.delete("/curricula/{curriculum_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Supprimer un programme pédagogique")
def delete_curriculum(curriculum_id: UUID, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    svc.delete_curriculum(conn, actor, curriculum_id)
    return _no_content()


@router.post("/curricula/{curriculum_id}/duplicate", response_model=CurriculumDetail, status_code=201,
             responses=ERRORS, summary="Copier un programme vers une autre année ou une nouvelle version")
def duplicate_curriculum(curriculum_id: UUID, body: CurriculumDuplicate, actor: Actor = Depends(writer),
                         conn: psycopg.Connection = Depends(get_db)):
    return svc.duplicate_curriculum(conn, actor, curriculum_id, body)


@router.post("/curricula/{curriculum_id}/subjects", response_model=CurriculumDetail, status_code=201,
             responses=ERRORS, summary="Ajouter une matière au programme")
def add_curriculum_subject(curriculum_id: UUID, body: CurriculumSubjectCreate, actor: Actor = Depends(writer),
                           conn: psycopg.Connection = Depends(get_db)):
    return svc.add_curriculum_subject(conn, actor, curriculum_id, body)


@router.patch("/curricula/{curriculum_id}/subjects/{item_id}", response_model=CurriculumDetail, responses=ERRORS,
              summary="Modifier une matière du programme (semestre, coefficient, crédits)")
def update_curriculum_subject(curriculum_id: UUID, item_id: UUID, body: CurriculumSubjectUpdate,
                              actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    return svc.update_curriculum_subject(conn, actor, curriculum_id, item_id, body)


@router.delete("/curricula/{curriculum_id}/subjects/{item_id}", response_model=CurriculumDetail, responses=ERRORS,
               summary="Retirer une matière du programme")
def remove_curriculum_subject(curriculum_id: UUID, item_id: UUID, actor: Actor = Depends(writer),
                              conn: psycopg.Connection = Depends(get_db)):
    return svc.remove_curriculum_subject(conn, actor, curriculum_id, item_id)
