"""Gestion des formations et des programmes (Membre 3) : formations, spécialités,
programmes pédagogiques, matières. Les tarifs et conditions d'admission sont dans
tuition_admission_service.py.

Portée : un responsable (iit_manager / isb_manager) ne voit et ne modifie que les formations de son
école ; l'administrateur voit tout ; la direction consulte sans modifier. Chaque écriture est tracée
dans audit_log.
"""
import unicodedata
from uuid import UUID

import psycopg

from app.core.errors import ForbiddenError, NotFoundError, UnprocessableError
from app.core.security import Actor
from app.schemas.catalog import (CYCLE_LABELS, CurriculumCreate, CurriculumDetail, CurriculumDuplicate,
                                 CurriculumOut, CurriculumSubjectCreate, CurriculumSubjectOut,
                                 CurriculumSubjectUpdate, CurriculumUpdate, InstitutionOut, ProgramCreate,
                                 ProgramOut, ProgramUpdate, SpecialtyCreate, SpecialtyOut, SpecialtyUpdate,
                                 SubjectCreate, SubjectOut, SubjectUpdate)
from app.schemas.common import Page
from app.services.db_utils import (Where, audit, delete_row, fetch_page, insert_row, translate_db_errors,
                                   update_row)

# ---------------------------------------------------------------------------
# Accès
# ---------------------------------------------------------------------------


def program_institution(conn: psycopg.Connection, program_id: UUID) -> UUID:
    row = conn.execute("SELECT institution_id FROM program WHERE id = %s", (program_id,)).fetchone()
    if not row:
        raise NotFoundError("Formation introuvable.")
    return row["institution_id"]


def ensure_can_read(actor: Actor, institution_id: UUID) -> None:
    scope = actor.scoped_institution_id()
    if scope is not None and scope != institution_id:
        raise ForbiddenError("Cette formation appartient à une autre école.")


def ensure_can_manage(actor: Actor, institution_id: UUID) -> None:
    if not actor.can_manage_institution(institution_id):
        raise ForbiddenError("Vous ne pouvez modifier que les formations de votre école.")


def ensure_can_manage_program(conn: psycopg.Connection, actor: Actor, program_id: UUID) -> UUID:
    institution_id = program_institution(conn, program_id)
    ensure_can_manage(actor, institution_id)
    return institution_id


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn").lower()


def resolve_cycle(level: str | None) -> str | None:
    """Accepte le code (engineering) ou le libellé (Ingénierie, ingenierie)."""
    if not level:
        return None
    key = _strip_accents(level.strip())
    for code, label in CYCLE_LABELS.items():
        if key in (code, _strip_accents(label)):
            return code
    raise UnprocessableError(f"Niveau inconnu : {level}. Valeurs : {', '.join(CYCLE_LABELS.values())}.")


# ---------------------------------------------------------------------------
# Écoles
# ---------------------------------------------------------------------------


def list_institutions(conn: psycopg.Connection) -> list[InstitutionOut]:
    rows = conn.execute("SELECT id, code, name FROM institution ORDER BY code").fetchall()
    return [InstitutionOut(**r) for r in rows]


# ---------------------------------------------------------------------------
# Formations
# ---------------------------------------------------------------------------
PROGRAM_SELECT = """
SELECT p.id, p.institution_id, i.code AS school, i.name AS institution_name, p.code, p.name, p.description,
       p.cycle, p.duration_years, p.degree, p.capacity, p.teaching_languages, p.career_outcomes, p.is_active,
       (SELECT count(*) FROM specialty s WHERE s.program_id = p.id) AS specialties_count,
       p.created_at, p.updated_at"""
PROGRAM_FROM = " FROM program p JOIN institution i ON i.id = p.institution_id"
PROGRAM_SORTS = {
    "name": "p.name", "-name": "p.name DESC", "code": "p.code", "-code": "p.code DESC",
    "school": "i.code, p.name", "duration": "p.duration_years NULLS LAST, p.name",
    "created_at": "p.created_at", "-created_at": "p.created_at DESC",
    "updated_at": "p.updated_at", "-updated_at": "p.updated_at DESC",
}


def program_filters(q: str | None = None, school: str | None = None, level: str | None = None,
                    cycle: str | None = None, language: str | None = None, is_active: bool | None = None,
                    institution_id: UUID | None = None) -> Where:
    w = Where()
    w.search(q, "p.name", "p.code", "p.description", "p.career_outcomes", "p.degree")
    w.add_if(school and school.upper(), "i.code = %s")
    w.add_if(resolve_cycle(cycle or level), "p.cycle = %s")
    w.add_if(language and language.lower(), "%s = ANY (p.teaching_languages)")
    w.add_if(is_active, "p.is_active = %s")
    w.add_if(institution_id, "p.institution_id = %s")
    return w


def list_programs(conn: psycopg.Connection, actor: Actor, *, q=None, school=None, level=None, cycle=None,
                  language=None, is_active=None, sort="name", page=1, size=20) -> Page[ProgramOut]:
    w = program_filters(q, school, level, cycle, language, is_active, actor.scoped_institution_id())
    rows, total = fetch_page(conn, PROGRAM_SELECT, PROGRAM_FROM, w, PROGRAM_SORTS.get(sort, "p.name"), page, size)
    return Page[ProgramOut](items=[ProgramOut(**r) for r in rows], total=total, page=page, size=size)


def get_program(conn: psycopg.Connection, program_id: UUID, actor: Actor | None = None) -> ProgramOut:
    row = conn.execute(f"{PROGRAM_SELECT}{PROGRAM_FROM} WHERE p.id = %s", (program_id,)).fetchone()
    if not row:
        raise NotFoundError("Formation introuvable.")
    if actor:
        ensure_can_read(actor, row["institution_id"])
    return ProgramOut(**row)


def create_program(conn: psycopg.Connection, actor: Actor, data: ProgramCreate) -> ProgramOut:
    values = data.model_dump()
    if actor.is_manager:
        if values["institution_id"] not in (None, actor.institution_id):
            raise ForbiddenError("Vous ne pouvez créer des formations que pour votre école.")
        values["institution_id"] = actor.institution_id
    elif values["institution_id"] is None:
        raise UnprocessableError("Choisissez l'école de la formation.", [{"field": "institution_id"}])
    with translate_db_errors(), conn.transaction():
        program_id = insert_row(conn, "program", values)
        audit(conn, actor, "catalog.program.create", "program", program_id, {"code": values["code"]})
    return get_program(conn, program_id)


def update_program(conn: psycopg.Connection, actor: Actor, program_id: UUID, data: ProgramUpdate) -> ProgramOut:
    ensure_can_manage_program(conn, actor, program_id)
    changes = data.changes()
    if "institution_id" in changes:
        ensure_can_manage(actor, changes["institution_id"])
    with translate_db_errors(), conn.transaction():
        update_row(conn, "program", program_id, changes)
        audit(conn, actor, "catalog.program.update", "program", program_id, changes)
    return get_program(conn, program_id)


def delete_program(conn: psycopg.Connection, actor: Actor, program_id: UUID) -> None:
    ensure_can_manage_program(conn, actor, program_id)
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "program", program_id, "Formation introuvable.")
        audit(conn, actor, "catalog.program.delete", "program", program_id)


# ---------------------------------------------------------------------------
# Spécialités
# ---------------------------------------------------------------------------
SPECIALTY_SELECT = """
SELECT s.id, s.program_id, p.code AS program_code, p.name AS program_name, i.code AS school,
       s.name, s.description, s.is_active,
       (SELECT count(*) FROM curriculum c WHERE c.specialty_id = s.id) AS curricula_count,
       s.created_at, s.updated_at"""
SPECIALTY_FROM = (" FROM specialty s JOIN program p ON p.id = s.program_id"
                  " JOIN institution i ON i.id = p.institution_id")


def list_specialties(conn: psycopg.Connection, actor: Actor, *, program_id=None, q=None, school=None,
                     is_active=None, page=1, size=50) -> Page[SpecialtyOut]:
    if program_id:
        ensure_can_read(actor, program_institution(conn, program_id))
    w = Where().add_if(program_id, "s.program_id = %s").search(q, "s.name", "s.description", "p.name")
    w.add_if(school and school.upper(), "i.code = %s").add_if(is_active, "s.is_active = %s")
    w.add_if(actor.scoped_institution_id(), "p.institution_id = %s")
    rows, total = fetch_page(conn, SPECIALTY_SELECT, SPECIALTY_FROM, w, "p.name, s.name", page, size)
    return Page[SpecialtyOut](items=[SpecialtyOut(**r) for r in rows], total=total, page=page, size=size)


def get_specialty(conn: psycopg.Connection, specialty_id: UUID, actor: Actor | None = None) -> SpecialtyOut:
    row = conn.execute(f"{SPECIALTY_SELECT}, p.institution_id{SPECIALTY_FROM} WHERE s.id = %s",
                       (specialty_id,)).fetchone()
    if not row:
        raise NotFoundError("Spécialité introuvable.")
    if actor:
        ensure_can_read(actor, row["institution_id"])
    return SpecialtyOut(**row)


def _specialty_program(conn: psycopg.Connection, specialty_id: UUID) -> UUID:
    row = conn.execute("SELECT program_id FROM specialty WHERE id = %s", (specialty_id,)).fetchone()
    if not row:
        raise NotFoundError("Spécialité introuvable.")
    return row["program_id"]


def create_specialty(conn: psycopg.Connection, actor: Actor, program_id: UUID, data: SpecialtyCreate) -> SpecialtyOut:
    ensure_can_manage_program(conn, actor, program_id)
    with translate_db_errors(), conn.transaction():
        specialty_id = insert_row(conn, "specialty", {"program_id": program_id, **data.model_dump()})
        audit(conn, actor, "catalog.specialty.create", "specialty", specialty_id, {"name": data.name})
    return get_specialty(conn, specialty_id)


def update_specialty(conn: psycopg.Connection, actor: Actor, specialty_id: UUID,
                     data: SpecialtyUpdate) -> SpecialtyOut:
    ensure_can_manage_program(conn, actor, _specialty_program(conn, specialty_id))
    changes = data.changes()
    with translate_db_errors(), conn.transaction():
        update_row(conn, "specialty", specialty_id, changes)
        audit(conn, actor, "catalog.specialty.update", "specialty", specialty_id, changes)
    return get_specialty(conn, specialty_id)


def delete_specialty(conn: psycopg.Connection, actor: Actor, specialty_id: UUID) -> None:
    ensure_can_manage_program(conn, actor, _specialty_program(conn, specialty_id))
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "specialty", specialty_id, "Spécialité introuvable.")
        audit(conn, actor, "catalog.specialty.delete", "specialty", specialty_id)


# ---------------------------------------------------------------------------
# Matières
# ---------------------------------------------------------------------------
SUBJECT_SELECT = """
SELECT sb.id, sb.code, sb.name, sb.description,
       (SELECT count(DISTINCT cs.curriculum_id) FROM curriculum_subject cs WHERE cs.subject_id = sb.id) AS usage_count,
       sb.created_at, sb.updated_at"""
SUBJECT_SORTS = {"code": "sb.code", "name": "sb.name", "-name": "sb.name DESC", "-created_at": "sb.created_at DESC"}


def list_subjects(conn: psycopg.Connection, *, q=None, program_id=None, curriculum_id=None, sort="code",
                  page=1, size=50) -> Page[SubjectOut]:
    w = Where().search(q, "sb.code", "sb.name", "sb.description")
    w.add_if(curriculum_id, "EXISTS (SELECT 1 FROM curriculum_subject cs WHERE cs.subject_id = sb.id "
                            "AND cs.curriculum_id = %s)")
    w.add_if(program_id, "EXISTS (SELECT 1 FROM curriculum_subject cs JOIN curriculum c ON c.id = cs.curriculum_id "
                         "WHERE cs.subject_id = sb.id AND c.program_id = %s)")
    rows, total = fetch_page(conn, SUBJECT_SELECT, " FROM subject sb", w, SUBJECT_SORTS.get(sort, "sb.code"),
                             page, size)
    return Page[SubjectOut](items=[SubjectOut(**r) for r in rows], total=total, page=page, size=size)


def get_subject(conn: psycopg.Connection, subject_id: UUID) -> SubjectOut:
    row = conn.execute(f"{SUBJECT_SELECT} FROM subject sb WHERE sb.id = %s", (subject_id,)).fetchone()
    if not row:
        raise NotFoundError("Matière introuvable.")
    return SubjectOut(**row)


def create_subject(conn: psycopg.Connection, actor: Actor, data: SubjectCreate) -> SubjectOut:
    with translate_db_errors(), conn.transaction():
        subject_id = insert_row(conn, "subject", data.model_dump())
        audit(conn, actor, "catalog.subject.create", "subject", subject_id, {"code": data.code})
    return get_subject(conn, subject_id)


def update_subject(conn: psycopg.Connection, actor: Actor, subject_id: UUID, data: SubjectUpdate) -> SubjectOut:
    get_subject(conn, subject_id)
    changes = data.changes()
    with translate_db_errors(), conn.transaction():
        update_row(conn, "subject", subject_id, changes)
        audit(conn, actor, "catalog.subject.update", "subject", subject_id, changes)
    return get_subject(conn, subject_id)


def delete_subject(conn: psycopg.Connection, actor: Actor, subject_id: UUID) -> None:
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "subject", subject_id, "Matière introuvable.")
        audit(conn, actor, "catalog.subject.delete", "subject", subject_id)


# ---------------------------------------------------------------------------
# Programmes pédagogiques
# ---------------------------------------------------------------------------
CURRICULUM_SELECT = """
SELECT c.id, c.program_id, p.code AS program_code, p.name AS program_name, i.code AS school, p.institution_id,
       c.specialty_id, s.name AS specialty_name, c.academic_year, c.version, c.description, c.is_active,
       (SELECT count(*) FROM curriculum_subject cs WHERE cs.curriculum_id = c.id) AS subjects_count,
       (SELECT coalesce(sum(cs.credits), 0) FROM curriculum_subject cs WHERE cs.curriculum_id = c.id) AS total_credits,
       c.created_at, c.updated_at"""
CURRICULUM_FROM = (" FROM curriculum c JOIN program p ON p.id = c.program_id"
                   " JOIN institution i ON i.id = p.institution_id LEFT JOIN specialty s ON s.id = c.specialty_id")
CURRICULUM_SUBJECT_SELECT = """
SELECT cs.id, cs.curriculum_id, cs.subject_id, sb.code AS subject_code, sb.name AS subject_name,
       cs.study_year, cs.semester, cs.coefficient, cs.credits, cs.is_mandatory
  FROM curriculum_subject cs JOIN subject sb ON sb.id = cs.subject_id"""


def list_curricula(conn: psycopg.Connection, actor: Actor | None, *, program_id=None, specialty_id=None,
                   academic_year=None, is_active=None, school=None, q=None, page=1, size=50) -> Page[CurriculumOut]:
    w = Where().add_if(program_id, "c.program_id = %s").add_if(specialty_id, "c.specialty_id = %s")
    w.add_if(academic_year, "c.academic_year = %s").add_if(is_active, "c.is_active = %s")
    w.add_if(school and school.upper(), "i.code = %s").search(q, "p.name", "p.code", "s.name", "c.description")
    if actor:
        w.add_if(actor.scoped_institution_id(), "p.institution_id = %s")
    rows, total = fetch_page(conn, CURRICULUM_SELECT, CURRICULUM_FROM, w,
                             "p.name, c.academic_year DESC, s.name NULLS FIRST, c.version DESC", page, size)
    return Page[CurriculumOut](items=[CurriculumOut(**r) for r in rows], total=total, page=page, size=size)


def curriculum_subjects(conn: psycopg.Connection, curriculum_ids: list[UUID]) -> dict[UUID, list[CurriculumSubjectOut]]:
    result: dict[UUID, list[CurriculumSubjectOut]] = {cid: [] for cid in curriculum_ids}
    if curriculum_ids:
        rows = conn.execute(f"{CURRICULUM_SUBJECT_SELECT} WHERE cs.curriculum_id = ANY(%s) "
                            "ORDER BY cs.study_year, cs.semester, sb.name", (curriculum_ids,)).fetchall()
        for r in rows:
            result[r["curriculum_id"]].append(CurriculumSubjectOut(**r))
    return result


def get_curriculum(conn: psycopg.Connection, curriculum_id: UUID, actor: Actor | None = None) -> CurriculumDetail:
    row = conn.execute(f"{CURRICULUM_SELECT}{CURRICULUM_FROM} WHERE c.id = %s", (curriculum_id,)).fetchone()
    if not row:
        raise NotFoundError("Programme pédagogique introuvable.")
    if actor:
        ensure_can_read(actor, row["institution_id"])
    return CurriculumDetail(**row, subjects=curriculum_subjects(conn, [curriculum_id])[curriculum_id])


def _curriculum_row(conn: psycopg.Connection, curriculum_id: UUID) -> dict:
    row = conn.execute("SELECT id, program_id, specialty_id, academic_year, version, is_active, description "
                       "FROM curriculum WHERE id = %s", (curriculum_id,)).fetchone()
    if not row:
        raise NotFoundError("Programme pédagogique introuvable.")
    return row


def _deactivate_siblings(conn: psycopg.Connection, program_id: UUID, specialty_id: UUID | None,
                         academic_year: str, except_id: UUID | None) -> None:
    """Une seule version active par (formation, spécialité, année) : activer l'une désactive les autres."""
    conn.execute(
        """UPDATE curriculum SET is_active = false
            WHERE program_id = %s AND specialty_id IS NOT DISTINCT FROM %s AND academic_year = %s
              AND is_active AND id IS DISTINCT FROM %s""",
        (program_id, specialty_id, academic_year, except_id))


def create_curriculum(conn: psycopg.Connection, actor: Actor, data: CurriculumCreate) -> CurriculumDetail:
    ensure_can_manage_program(conn, actor, data.program_id)
    values = data.model_dump()
    with translate_db_errors(), conn.transaction():
        if values["is_active"]:
            _deactivate_siblings(conn, data.program_id, data.specialty_id, data.academic_year, None)
        curriculum_id = insert_row(conn, "curriculum", values)
        audit(conn, actor, "catalog.curriculum.create", "curriculum", curriculum_id,
              {"program_id": data.program_id, "academic_year": data.academic_year, "version": data.version})
    return get_curriculum(conn, curriculum_id)


def update_curriculum(conn: psycopg.Connection, actor: Actor, curriculum_id: UUID,
                      data: CurriculumUpdate) -> CurriculumDetail:
    current = _curriculum_row(conn, curriculum_id)
    ensure_can_manage_program(conn, actor, current["program_id"])
    changes = data.changes()
    merged = {**current, **changes}
    with translate_db_errors(), conn.transaction():
        if merged["is_active"]:
            _deactivate_siblings(conn, current["program_id"], merged["specialty_id"], merged["academic_year"],
                                 curriculum_id)
        update_row(conn, "curriculum", curriculum_id, changes)
        audit(conn, actor, "catalog.curriculum.update", "curriculum", curriculum_id, changes)
    return get_curriculum(conn, curriculum_id)


def delete_curriculum(conn: psycopg.Connection, actor: Actor, curriculum_id: UUID) -> None:
    ensure_can_manage_program(conn, actor, _curriculum_row(conn, curriculum_id)["program_id"])
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "curriculum", curriculum_id, "Programme pédagogique introuvable.")
        audit(conn, actor, "catalog.curriculum.delete", "curriculum", curriculum_id)


def duplicate_curriculum(conn: psycopg.Connection, actor: Actor, curriculum_id: UUID,
                         data: CurriculumDuplicate) -> CurriculumDetail:
    """Copie un programme (et ses matières) vers une nouvelle année ou une nouvelle version."""
    source = _curriculum_row(conn, curriculum_id)
    ensure_can_manage_program(conn, actor, source["program_id"])
    version = data.version
    if version is None:
        version = conn.execute(
            """SELECT coalesce(max(version), 0) + 1 AS v FROM curriculum
                WHERE program_id = %s AND specialty_id IS NOT DISTINCT FROM %s AND academic_year = %s""",
            (source["program_id"], source["specialty_id"], data.academic_year)).fetchone()["v"]
    with translate_db_errors(), conn.transaction():
        if data.is_active:
            _deactivate_siblings(conn, source["program_id"], source["specialty_id"], data.academic_year, None)
        new_id = insert_row(conn, "curriculum", {
            "program_id": source["program_id"], "specialty_id": source["specialty_id"],
            "academic_year": data.academic_year, "version": version,
            "description": source["description"], "is_active": data.is_active})
        conn.execute(
            """INSERT INTO curriculum_subject (curriculum_id, subject_id, study_year, semester, coefficient,
                                              credits, is_mandatory)
               SELECT %s, subject_id, study_year, semester, coefficient, credits, is_mandatory
                 FROM curriculum_subject WHERE curriculum_id = %s""", (new_id, curriculum_id))
        audit(conn, actor, "catalog.curriculum.duplicate", "curriculum", new_id,
              {"source_id": curriculum_id, "academic_year": data.academic_year, "version": version})
    return get_curriculum(conn, new_id)


def add_curriculum_subject(conn: psycopg.Connection, actor: Actor, curriculum_id: UUID,
                           data: CurriculumSubjectCreate) -> CurriculumDetail:
    ensure_can_manage_program(conn, actor, _curriculum_row(conn, curriculum_id)["program_id"])
    with translate_db_errors(), conn.transaction():
        item_id = insert_row(conn, "curriculum_subject", {"curriculum_id": curriculum_id, **data.model_dump()})
        audit(conn, actor, "catalog.curriculum_subject.create", "curriculum_subject", item_id,
              {"curriculum_id": curriculum_id, "subject_id": data.subject_id})
    return get_curriculum(conn, curriculum_id)


def _curriculum_subject_owner(conn: psycopg.Connection, curriculum_id: UUID, item_id: UUID) -> None:
    row = conn.execute("SELECT 1 FROM curriculum_subject WHERE id = %s AND curriculum_id = %s",
                       (item_id, curriculum_id)).fetchone()
    if not row:
        raise NotFoundError("Matière introuvable dans ce programme.")


def update_curriculum_subject(conn: psycopg.Connection, actor: Actor, curriculum_id: UUID, item_id: UUID,
                              data: CurriculumSubjectUpdate) -> CurriculumDetail:
    ensure_can_manage_program(conn, actor, _curriculum_row(conn, curriculum_id)["program_id"])
    _curriculum_subject_owner(conn, curriculum_id, item_id)
    changes = data.changes()
    with translate_db_errors(), conn.transaction():
        update_row(conn, "curriculum_subject", item_id, changes)
        audit(conn, actor, "catalog.curriculum_subject.update", "curriculum_subject", item_id, changes)
    return get_curriculum(conn, curriculum_id)


def remove_curriculum_subject(conn: psycopg.Connection, actor: Actor, curriculum_id: UUID,
                              item_id: UUID) -> CurriculumDetail:
    ensure_can_manage_program(conn, actor, _curriculum_row(conn, curriculum_id)["program_id"])
    _curriculum_subject_owner(conn, curriculum_id, item_id)
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "curriculum_subject", item_id, "Matière introuvable dans ce programme.")
        audit(conn, actor, "catalog.curriculum_subject.delete", "curriculum_subject", item_id,
              {"curriculum_id": curriculum_id})
    return get_curriculum(conn, curriculum_id)
