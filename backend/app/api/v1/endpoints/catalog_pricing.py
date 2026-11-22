"""Routes « Tarifs et admission » (Membre 3 - SA-21) : responsables académiques et administrateur.

Frais de scolarité, modalités de paiement, conditions d'admission : CRUD + statut de publication
(draft / published / archived) + période de validité. Les candidats et l'agent IA lisent la version
officielle via /programs/{id}/tuition et /programs/{id}/admission.
"""
from datetime import date
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Query, Response

from app.core.security import CATALOG_READ_ROLES, CATALOG_WRITE_ROLES, Actor, require_roles
from app.db.session import get_db
from app.schemas.catalog import (AcademicYear, AdmissionRequirementCreate, AdmissionRequirementOut,
                                 AdmissionRequirementUpdate, FeeType, PaymentMethod, PaymentPlanCreate,
                                 PaymentPlanOut, PaymentPlanUpdate, PublicationStatus, PublicationStatusChange,
                                 RequirementCategory, RequirementKind, TuitionFeeCreate, TuitionFeeOut,
                                 TuitionFeeUpdate, Visibility)
from app.schemas.common import ErrorResponse, Page
from app.services import tuition_admission_service as svc

router = APIRouter(prefix="/catalog", tags=["Tarifs et admission"])

reader = require_roles(*CATALOG_READ_ROLES)
writer = require_roles(*CATALOG_WRITE_ROLES)
ERRORS = {
    404: {"model": ErrorResponse, "description": "Élément introuvable"},
    409: {"model": ErrorResponse, "description": "Doublon, ou élément archivé non modifiable"},
}
STATUS_DOC = ("published : visible par les candidats et l'agent IA pendant la période de validité ; "
              "draft : retiré (brouillon) ; archived : historique, non modifiable.")


def _publication_query(
    program_id: UUID | None = None,
    school: str | None = Query(None, description="IIT ou ISB"),
    academic_year: AcademicYear | None = None,
    status: PublicationStatus | None = Query(None, description="draft, published, archived"),
    visibility: Visibility | None = Query(
        None, description="visible (en ligne aujourd'hui), scheduled (pas encore valide), expired, draft, archived"),
    valid_on: date | None = Query(None, description="Officiel (publié et valide) à cette date"),
    q: str | None = Query(None, description="Recherche texte"),
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=100),
) -> dict:
    return {"program_id": program_id, "school": school, "academic_year": academic_year, "status": status,
            "visibility": visibility, "valid_on": valid_on, "q": q, "page": page, "size": size}


# --- Conditions d'admission -----------------------------------------------------------------
@router.get("/admission-requirements", response_model=Page[AdmissionRequirementOut],
            summary="Rechercher les conditions d'admission (brouillons compris)")
def list_admission_requirements(category: RequirementCategory | None = None, kind: RequirementKind | None = None,
                                filters: dict = Depends(_publication_query), actor: Actor = Depends(reader),
                                conn: psycopg.Connection = Depends(get_db)):
    return svc.list_admission_requirements(conn, actor, category=category, kind=kind, **filters)


@router.post("/admission-requirements", response_model=AdmissionRequirementOut, status_code=201, responses=ERRORS,
             summary="Ajouter une condition d'admission (créée en brouillon)")
def create_admission_requirement(body: AdmissionRequirementCreate, actor: Actor = Depends(writer),
                                 conn: psycopg.Connection = Depends(get_db)):
    return svc.create_admission_requirement(conn, actor, body)


@router.get("/admission-requirements/{req_id}", response_model=AdmissionRequirementOut, responses=ERRORS,
            summary="Consulter une condition d'admission")
def get_admission_requirement(req_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_admission_requirement(conn, req_id, actor)


@router.patch("/admission-requirements/{req_id}", response_model=AdmissionRequirementOut, responses=ERRORS,
              summary="Modifier une condition d'admission")
def update_admission_requirement(req_id: UUID, body: AdmissionRequirementUpdate, actor: Actor = Depends(writer),
                                 conn: psycopg.Connection = Depends(get_db)):
    return svc.update_admission_requirement(conn, actor, req_id, body)


@router.delete("/admission-requirements/{req_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Supprimer une condition d'admission")
def delete_admission_requirement(req_id: UUID, actor: Actor = Depends(writer),
                                 conn: psycopg.Connection = Depends(get_db)):
    svc.delete_admission_requirement(conn, actor, req_id)
    return Response(status_code=204)


@router.post("/admission-requirements/{req_id}/status", response_model=AdmissionRequirementOut, responses=ERRORS,
             summary="Publier, retirer ou archiver une condition", description=STATUS_DOC)
def set_admission_requirement_status(req_id: UUID, body: PublicationStatusChange, actor: Actor = Depends(writer),
                                     conn: psycopg.Connection = Depends(get_db)):
    return svc.set_admission_requirement_status(conn, actor, req_id, body.status)


# --- Frais de scolarité --------------------------------------------------------------------
@router.get("/tuition-fees", response_model=Page[TuitionFeeOut], summary="Rechercher les tarifs (brouillons compris)")
def list_tuition_fees(fee_type: FeeType | None = None, filters: dict = Depends(_publication_query),
                      actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.list_tuition_fees(conn, actor, fee_type=fee_type, **filters)


@router.post("/tuition-fees", response_model=TuitionFeeOut, status_code=201, responses=ERRORS,
             summary="Ajouter un tarif (créé en brouillon)")
def create_tuition_fee(body: TuitionFeeCreate, actor: Actor = Depends(writer),
                       conn: psycopg.Connection = Depends(get_db)):
    return svc.create_tuition_fee(conn, actor, body)


@router.get("/tuition-fees/{fee_id}", response_model=TuitionFeeOut, responses=ERRORS, summary="Consulter un tarif")
def get_tuition_fee(fee_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_tuition_fee(conn, fee_id, actor)


@router.patch("/tuition-fees/{fee_id}", response_model=TuitionFeeOut, responses=ERRORS, summary="Modifier un tarif")
def update_tuition_fee(fee_id: UUID, body: TuitionFeeUpdate, actor: Actor = Depends(writer),
                       conn: psycopg.Connection = Depends(get_db)):
    return svc.update_tuition_fee(conn, actor, fee_id, body)


@router.delete("/tuition-fees/{fee_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Supprimer un tarif")
def delete_tuition_fee(fee_id: UUID, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    svc.delete_tuition_fee(conn, actor, fee_id)
    return Response(status_code=204)


@router.post("/tuition-fees/{fee_id}/status", response_model=TuitionFeeOut, responses=ERRORS,
             summary="Publier, retirer ou archiver un tarif", description=STATUS_DOC)
def set_tuition_fee_status(fee_id: UUID, body: PublicationStatusChange, actor: Actor = Depends(writer),
                           conn: psycopg.Connection = Depends(get_db)):
    return svc.set_tuition_fee_status(conn, actor, fee_id, body.status)


# --- Modalités de paiement -------------------------------------------------------------------
@router.get("/payment-plans", response_model=Page[PaymentPlanOut],
            summary="Rechercher les modalités de paiement (brouillons compris)")
def list_payment_plans(payment_method: PaymentMethod | None = None, filters: dict = Depends(_publication_query),
                       actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.list_payment_plans(conn, actor, payment_method=payment_method, **filters)


@router.post("/payment-plans", response_model=PaymentPlanOut, status_code=201, responses=ERRORS,
             summary="Ajouter une modalité de paiement et ses échéances (créée en brouillon)")
def create_payment_plan(body: PaymentPlanCreate, actor: Actor = Depends(writer),
                        conn: psycopg.Connection = Depends(get_db)):
    return svc.create_payment_plan(conn, actor, body)


@router.get("/payment-plans/{plan_id}", response_model=PaymentPlanOut, responses=ERRORS,
            summary="Consulter une modalité de paiement")
def get_payment_plan(plan_id: UUID, actor: Actor = Depends(reader), conn: psycopg.Connection = Depends(get_db)):
    return svc.get_payment_plan(conn, plan_id, actor)


@router.patch("/payment-plans/{plan_id}", response_model=PaymentPlanOut, responses=ERRORS,
              summary="Modifier une modalité (installments remplace toutes les échéances)")
def update_payment_plan(plan_id: UUID, body: PaymentPlanUpdate, actor: Actor = Depends(writer),
                        conn: psycopg.Connection = Depends(get_db)):
    return svc.update_payment_plan(conn, actor, plan_id, body)


@router.delete("/payment-plans/{plan_id}", status_code=204, response_class=Response, responses=ERRORS,
               summary="Supprimer une modalité de paiement")
def delete_payment_plan(plan_id: UUID, actor: Actor = Depends(writer), conn: psycopg.Connection = Depends(get_db)):
    svc.delete_payment_plan(conn, actor, plan_id)
    return Response(status_code=204)


@router.post("/payment-plans/{plan_id}/status", response_model=PaymentPlanOut, responses=ERRORS,
             summary="Publier, retirer ou archiver une modalité", description=STATUS_DOC)
def set_payment_plan_status(plan_id: UUID, body: PublicationStatusChange, actor: Actor = Depends(writer),
                            conn: psycopg.Connection = Depends(get_db)):
    return svc.set_payment_plan_status(conn, actor, plan_id, body.status)
