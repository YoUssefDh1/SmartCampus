"""Tarifs, modalités de paiement et conditions d'admission (Membre 3 - SA-21).

Deux usages :
  * Gestion (responsables / admin) : CRUD + workflow de publication draft -> published -> archived,
    avec période de validité. Lecture de toutes les versions (brouillons compris).
  * Consultation officielle (candidats, visiteurs, agent IA) : fonctions official_* qui lisent les vues
    v_official_* (migration 002) -> uniquement publié ET valide aujourd'hui ET formation active.
    L'agent IA (Membre 5) doit utiliser ces fonctions, ou les vues, et rien d'autre.
"""
from uuid import UUID

import psycopg

from app.core.errors import ConflictError, NotFoundError, UnprocessableError
from app.core.security import Actor
from app.schemas.catalog import (AdmissionRequirementCreate, AdmissionRequirementOut, AdmissionRequirementPublic,
                                 AdmissionRequirementUpdate, InstallmentIn, PaymentPlanCreate, PaymentPlanOut,
                                 PaymentPlanPublic, PaymentPlanUpdate, PublicationStatus, TuitionFeeCreate,
                                 TuitionFeeOut, TuitionFeePublic, TuitionFeeUpdate)
from app.schemas.common import Page
from app.services.catalog_service import ensure_can_manage_program, ensure_can_read
from app.services.db_utils import (Where, audit, delete_row, fetch_page, insert_row, translate_db_errors,
                                   update_row, visibility_sql)

# Les trois ressources partagent le même workflow ; seules les requêtes changent.
RESOURCES = {
    "admission_requirement": {"label": "Condition d'admission", "not_found": "Condition d'admission introuvable."},
    "tuition_fee": {"label": "Tarif", "not_found": "Tarif introuvable."},
    "payment_plan": {"label": "Modalité de paiement", "not_found": "Modalité de paiement introuvable."},
}

_PROGRAM_JOIN = " JOIN program p ON p.id = {a}.program_id JOIN institution i ON i.id = p.institution_id"
_PUBLICATION_COLS = ("{a}.status, " + "{vis} AS visibility, "
                     "{a}.valid_from, {a}.valid_until, {a}.published_at, {a}.published_by_id, "
                     "{a}.program_id, p.code AS program_code, p.name AS program_name, i.code AS school, "
                     "p.institution_id, {a}.created_at, {a}.updated_at")


def _pub_cols(alias: str) -> str:
    return _PUBLICATION_COLS.format(a=alias, vis=visibility_sql(alias))


def _publication_filters(w: Where, alias: str, actor: Actor, *, program_id, school, academic_year, status,
                         visibility, valid_on) -> Where:
    w.add_if(program_id, f"{alias}.program_id = %s").add_if(school and school.upper(), "i.code = %s")
    w.add_if(academic_year, f"{alias}.academic_year = %s").add_if(status, f"{alias}.status = %s")
    w.add_if(visibility, f"({visibility_sql(alias)}) = %s")
    w.add_if(valid_on, f"catalog_is_official({alias}.status, {alias}.valid_from, {alias}.valid_until, %s)")
    w.add_if(actor.scoped_institution_id(), "p.institution_id = %s")
    return w


def _owner(conn: psycopg.Connection, table: str, row_id: UUID) -> dict:
    row = conn.execute(f"SELECT program_id, status, valid_from, valid_until FROM {table} WHERE id = %s",
                       (row_id,)).fetchone()
    if not row:
        raise NotFoundError(RESOURCES[table]["not_found"])
    return row


def _ensure_editable(row: dict, table: str) -> None:
    if row["status"] == "archived":
        raise ConflictError(f"{RESOURCES[table]['label']} archivé(e) : remettez-le en brouillon avant de le modifier.")


def _set_status(conn: psycopg.Connection, actor: Actor, table: str, row_id: UUID, status: PublicationStatus) -> None:
    row = _owner(conn, table, row_id)
    ensure_can_manage_program(conn, actor, row["program_id"])
    if row["status"] == status:
        return
    if status == "published":
        expired = conn.execute("SELECT %s::date < current_date AS expired",
                               (row["valid_until"],)).fetchone()["expired"]
        if expired:
            raise UnprocessableError("La période de validité est déjà terminée : modifiez les dates avant de publier.")
        values = {"status": "published"}
        sql_extra = ", published_at = now(), published_by_id = %s"
        params = [actor.user_id]
    else:
        values = {"status": status}
        sql_extra = ", published_at = NULL, published_by_id = NULL"
        params = []
    with translate_db_errors(), conn.transaction():
        conn.execute(f"UPDATE {table} SET status = %s{sql_extra} WHERE id = %s",
                     [values["status"], *params, row_id])
        audit(conn, actor, f"catalog.{table}.{status}", table, row_id, {"from": row["status"], "to": status})


# ===========================================================================
# Conditions d'admission
# ===========================================================================
ADMISSION_SELECT = f"""
SELECT r.id, r.category, r.kind, r.description, r.min_average, r.accepted_bac_series, r.required_program_id,
       rp.name AS required_program_name, r.academic_year, r.is_mandatory, r.position, {_pub_cols('r')}"""
ADMISSION_FROM = (" FROM admission_requirement r" + _PROGRAM_JOIN.format(a="r")
                  + " LEFT JOIN program rp ON rp.id = r.required_program_id")


def list_admission_requirements(conn: psycopg.Connection, actor: Actor, *, program_id=None, school=None,
                                academic_year=None, category=None, kind=None, status=None, visibility=None,
                                valid_on=None, q=None, page=1, size=50) -> Page[AdmissionRequirementOut]:
    w = Where().add_if(category, "r.category = %s").add_if(kind, "r.kind = %s").search(q, "r.description", "p.name")
    _publication_filters(w, "r", actor, program_id=program_id, school=school, academic_year=None, status=status,
                         visibility=visibility, valid_on=valid_on)
    # Une condition sans année s'applique à toutes les années.
    w.add_if(academic_year, "(r.academic_year = %s OR r.academic_year IS NULL)")
    rows, total = fetch_page(conn, ADMISSION_SELECT, ADMISSION_FROM, w,
                             "p.name, r.category, r.position, r.created_at", page, size)
    return Page[AdmissionRequirementOut](items=[AdmissionRequirementOut(**r) for r in rows],
                                         total=total, page=page, size=size)


def get_admission_requirement(conn: psycopg.Connection, req_id: UUID,
                              actor: Actor | None = None) -> AdmissionRequirementOut:
    row = conn.execute(f"{ADMISSION_SELECT}{ADMISSION_FROM} WHERE r.id = %s", (req_id,)).fetchone()
    if not row:
        raise NotFoundError(RESOURCES["admission_requirement"]["not_found"])
    if actor:
        ensure_can_read(actor, row["institution_id"])
    return AdmissionRequirementOut(**row)


def create_admission_requirement(conn: psycopg.Connection, actor: Actor,
                                 data: AdmissionRequirementCreate) -> AdmissionRequirementOut:
    ensure_can_manage_program(conn, actor, data.program_id)
    if data.required_program_id == data.program_id:
        raise UnprocessableError("Une formation ne peut pas s'exiger elle-même.")
    with translate_db_errors(), conn.transaction():
        req_id = insert_row(conn, "admission_requirement", data.model_dump())
        audit(conn, actor, "catalog.admission_requirement.create", "admission_requirement", req_id,
              {"program_id": data.program_id, "kind": data.kind})
    return get_admission_requirement(conn, req_id)


def update_admission_requirement(conn: psycopg.Connection, actor: Actor, req_id: UUID,
                                 data: AdmissionRequirementUpdate) -> AdmissionRequirementOut:
    row = _owner(conn, "admission_requirement", req_id)
    ensure_can_manage_program(conn, actor, row["program_id"])
    _ensure_editable(row, "admission_requirement")
    changes = data.changes()
    if changes.get("required_program_id") == row["program_id"]:
        raise UnprocessableError("Une formation ne peut pas s'exiger elle-même.")
    with translate_db_errors(), conn.transaction():
        update_row(conn, "admission_requirement", req_id, changes)
        audit(conn, actor, "catalog.admission_requirement.update", "admission_requirement", req_id, changes)
    return get_admission_requirement(conn, req_id)


def delete_admission_requirement(conn: psycopg.Connection, actor: Actor, req_id: UUID) -> None:
    ensure_can_manage_program(conn, actor, _owner(conn, "admission_requirement", req_id)["program_id"])
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "admission_requirement", req_id, RESOURCES["admission_requirement"]["not_found"])
        audit(conn, actor, "catalog.admission_requirement.delete", "admission_requirement", req_id)


def set_admission_requirement_status(conn: psycopg.Connection, actor: Actor, req_id: UUID,
                                     status: PublicationStatus) -> AdmissionRequirementOut:
    _set_status(conn, actor, "admission_requirement", req_id, status)
    return get_admission_requirement(conn, req_id)


# ===========================================================================
# Frais de scolarité
# ===========================================================================
FEE_SELECT = f"""
SELECT f.id, f.academic_year, f.study_year, f.fee_type, f.amount, f.currency, f.description, {_pub_cols('f')}"""
FEE_FROM = " FROM tuition_fee f" + _PROGRAM_JOIN.format(a="f")


def list_tuition_fees(conn: psycopg.Connection, actor: Actor, *, program_id=None, school=None, academic_year=None,
                      fee_type=None, status=None, visibility=None, valid_on=None, q=None, page=1,
                      size=50) -> Page[TuitionFeeOut]:
    w = Where().add_if(fee_type, "f.fee_type = %s").search(q, "f.description", "p.name", "p.code")
    _publication_filters(w, "f", actor, program_id=program_id, school=school, academic_year=academic_year,
                         status=status, visibility=visibility, valid_on=valid_on)
    rows, total = fetch_page(conn, FEE_SELECT, FEE_FROM, w,
                             "p.name, f.academic_year DESC, f.fee_type, f.study_year NULLS FIRST", page, size)
    return Page[TuitionFeeOut](items=[TuitionFeeOut(**r) for r in rows], total=total, page=page, size=size)


def get_tuition_fee(conn: psycopg.Connection, fee_id: UUID, actor: Actor | None = None) -> TuitionFeeOut:
    row = conn.execute(f"{FEE_SELECT}{FEE_FROM} WHERE f.id = %s", (fee_id,)).fetchone()
    if not row:
        raise NotFoundError(RESOURCES["tuition_fee"]["not_found"])
    if actor:
        ensure_can_read(actor, row["institution_id"])
    return TuitionFeeOut(**row)


def create_tuition_fee(conn: psycopg.Connection, actor: Actor, data: TuitionFeeCreate) -> TuitionFeeOut:
    ensure_can_manage_program(conn, actor, data.program_id)
    with translate_db_errors(), conn.transaction():
        fee_id = insert_row(conn, "tuition_fee", data.model_dump())
        audit(conn, actor, "catalog.tuition_fee.create", "tuition_fee", fee_id,
              {"program_id": data.program_id, "fee_type": data.fee_type, "amount": data.amount})
    return get_tuition_fee(conn, fee_id)


def update_tuition_fee(conn: psycopg.Connection, actor: Actor, fee_id: UUID, data: TuitionFeeUpdate) -> TuitionFeeOut:
    row = _owner(conn, "tuition_fee", fee_id)
    ensure_can_manage_program(conn, actor, row["program_id"])
    _ensure_editable(row, "tuition_fee")
    changes = data.changes()
    with translate_db_errors(), conn.transaction():
        update_row(conn, "tuition_fee", fee_id, changes)
        audit(conn, actor, "catalog.tuition_fee.update", "tuition_fee", fee_id, changes)
    return get_tuition_fee(conn, fee_id)


def delete_tuition_fee(conn: psycopg.Connection, actor: Actor, fee_id: UUID) -> None:
    ensure_can_manage_program(conn, actor, _owner(conn, "tuition_fee", fee_id)["program_id"])
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "tuition_fee", fee_id, RESOURCES["tuition_fee"]["not_found"])
        audit(conn, actor, "catalog.tuition_fee.delete", "tuition_fee", fee_id)


def set_tuition_fee_status(conn: psycopg.Connection, actor: Actor, fee_id: UUID,
                           status: PublicationStatus) -> TuitionFeeOut:
    _set_status(conn, actor, "tuition_fee", fee_id, status)
    return get_tuition_fee(conn, fee_id)


# ===========================================================================
# Modalités de paiement
# ===========================================================================
INSTALLMENTS_JSON = """
coalesce((SELECT jsonb_agg(jsonb_build_object(
          'id', pi.id, 'position', pi.position, 'label', pi.label, 'due_date', pi.due_date,
          'due_description', pi.due_description, 'percentage', pi.percentage, 'amount', pi.amount)
          ORDER BY pi.position)
     FROM payment_installment pi WHERE pi.payment_plan_id = pp.id), '[]'::jsonb) AS installments"""
PLAN_SELECT = f"""
SELECT pp.id, pp.academic_year, pp.name, pp.description, pp.payment_methods, pp.discount_percent, pp.currency,
       pp.conditions, pp.position, {INSTALLMENTS_JSON}, {_pub_cols('pp')}"""
PLAN_FROM = " FROM payment_plan pp" + _PROGRAM_JOIN.format(a="pp")


def list_payment_plans(conn: psycopg.Connection, actor: Actor, *, program_id=None, school=None, academic_year=None,
                       payment_method=None, status=None, visibility=None, valid_on=None, q=None, page=1,
                       size=50) -> Page[PaymentPlanOut]:
    w = Where().add_if(payment_method, "%s = ANY (pp.payment_methods)")
    w.search(q, "pp.name", "pp.description", "p.name")
    _publication_filters(w, "pp", actor, program_id=program_id, school=school, academic_year=academic_year,
                         status=status, visibility=visibility, valid_on=valid_on)
    rows, total = fetch_page(conn, PLAN_SELECT, PLAN_FROM, w, "p.name, pp.academic_year DESC, pp.position, pp.name",
                             page, size)
    return Page[PaymentPlanOut](items=[PaymentPlanOut(**r) for r in rows], total=total, page=page, size=size)


def get_payment_plan(conn: psycopg.Connection, plan_id: UUID, actor: Actor | None = None) -> PaymentPlanOut:
    row = conn.execute(f"{PLAN_SELECT}{PLAN_FROM} WHERE pp.id = %s", (plan_id,)).fetchone()
    if not row:
        raise NotFoundError(RESOURCES["payment_plan"]["not_found"])
    if actor:
        ensure_can_read(actor, row["institution_id"])
    return PaymentPlanOut(**row)


def _replace_installments(conn: psycopg.Connection, plan_id: UUID, installments: list[InstallmentIn]) -> None:
    conn.execute("DELETE FROM payment_installment WHERE payment_plan_id = %s", (plan_id,))
    for position, item in enumerate(installments, start=1):
        insert_row(conn, "payment_installment", {"payment_plan_id": plan_id, "position": position,
                                                 **item.model_dump()})


def create_payment_plan(conn: psycopg.Connection, actor: Actor, data: PaymentPlanCreate) -> PaymentPlanOut:
    ensure_can_manage_program(conn, actor, data.program_id)
    values = data.model_dump(exclude={"installments"})
    with translate_db_errors(), conn.transaction():
        plan_id = insert_row(conn, "payment_plan", values)
        _replace_installments(conn, plan_id, data.installments)
        audit(conn, actor, "catalog.payment_plan.create", "payment_plan", plan_id,
              {"program_id": data.program_id, "name": data.name, "installments": len(data.installments)})
    return get_payment_plan(conn, plan_id)


def update_payment_plan(conn: psycopg.Connection, actor: Actor, plan_id: UUID,
                        data: PaymentPlanUpdate) -> PaymentPlanOut:
    row = _owner(conn, "payment_plan", plan_id)
    ensure_can_manage_program(conn, actor, row["program_id"])
    _ensure_editable(row, "payment_plan")
    changes = data.changes()
    installments = changes.pop("installments", None)
    with translate_db_errors(), conn.transaction():
        update_row(conn, "payment_plan", plan_id, changes)
        if installments is not None:
            _replace_installments(conn, plan_id, data.installments or [])
            changes["installments"] = len(installments)
        audit(conn, actor, "catalog.payment_plan.update", "payment_plan", plan_id, changes)
    return get_payment_plan(conn, plan_id)


def delete_payment_plan(conn: psycopg.Connection, actor: Actor, plan_id: UUID) -> None:
    ensure_can_manage_program(conn, actor, _owner(conn, "payment_plan", plan_id)["program_id"])
    with translate_db_errors(deleting=True), conn.transaction():
        delete_row(conn, "payment_plan", plan_id, RESOURCES["payment_plan"]["not_found"])
        audit(conn, actor, "catalog.payment_plan.delete", "payment_plan", plan_id)


def set_payment_plan_status(conn: psycopg.Connection, actor: Actor, plan_id: UUID,
                            status: PublicationStatus) -> PaymentPlanOut:
    _set_status(conn, actor, "payment_plan", plan_id, status)
    return get_payment_plan(conn, plan_id)


# ===========================================================================
# Consultation OFFICIELLE (candidats, visiteurs, agent IA) : vues v_official_*
# ===========================================================================


def official_admission_requirements(conn: psycopg.Connection, program_id: UUID,
                                    academic_year: str | None = None) -> list[AdmissionRequirementPublic]:
    w = Where().add("program_id = %s", program_id)
    w.add_if(academic_year, "(academic_year = %s OR academic_year IS NULL)")
    rows = conn.execute(f"SELECT * FROM v_official_admission_requirement{w.sql()} "
                        "ORDER BY category, position, description", w.params).fetchall()
    return [AdmissionRequirementPublic(**r) for r in rows]


def official_tuition_fees(conn: psycopg.Connection, program_id: UUID,
                          academic_year: str | None = None) -> list[TuitionFeePublic]:
    w = Where().add("program_id = %s", program_id).add_if(academic_year, "academic_year = %s")
    rows = conn.execute(
        f"""SELECT * FROM v_official_tuition_fee{w.sql()}
            ORDER BY academic_year, CASE fee_type WHEN 'application' THEN 1 WHEN 'registration' THEN 2
                                                  WHEN 'tuition' THEN 3 ELSE 4 END, study_year NULLS FIRST""",
        w.params).fetchall()
    return [TuitionFeePublic(**r) for r in rows]


def official_payment_plans(conn: psycopg.Connection, program_id: UUID,
                           academic_year: str | None = None) -> list[PaymentPlanPublic]:
    w = Where().add("program_id = %s", program_id).add_if(academic_year, "academic_year = %s")
    rows = conn.execute(f"SELECT * FROM v_official_payment_plan{w.sql()} ORDER BY academic_year, position, name",
                        w.params).fetchall()
    return [PaymentPlanPublic(**r) for r in rows]
