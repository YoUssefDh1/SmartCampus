"""Schémas publics du catalogue (candidats, visiteurs, agent IA).

Ne contiennent QUE des informations officielles : publiées et valides à la date du jour
(vues v_official_* de la migration 002). Aucun brouillon, aucune donnée d'audit.
"""
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.catalog import (AdmissionRequirementPublic, CurriculumSubjectOut, PaymentPlanPublic, ProgramOut,
                                 TuitionFeePublic)


class Program(ProgramOut):
    """Formation dans la liste publique."""

    tuition_from: float | None = Field(None, description="Plus petits frais de scolarité officiels en vigueur")
    tuition_currency: str | None = None


class SpecialtyPublic(BaseModel):
    id: UUID
    name: str
    description: str | None


class ProgramDetail(Program):
    """Fiche complète : tout ce que le candidat ou l'agent IA peut affirmer sur la formation."""

    specialties: list[SpecialtyPublic] = []
    admission_requirements: list[AdmissionRequirementPublic] = []
    tuition_fees: list[TuitionFeePublic] = []
    payment_plans: list[PaymentPlanPublic] = []


class ProgramTuition(BaseModel):
    program_id: UUID
    program_name: str
    school: str
    academic_year: str | None = Field(None, description="Filtre appliqué (vide = toutes les années en vigueur)")
    fees: list[TuitionFeePublic]
    payment_plans: list[PaymentPlanPublic]


class ProgramAdmission(BaseModel):
    program_id: UUID
    program_name: str
    school: str
    academic_year: str | None
    requirements: list[AdmissionRequirementPublic]


class CurriculumPublic(BaseModel):
    id: UUID
    specialty_id: UUID | None
    specialty_name: str | None
    academic_year: str
    version: int
    description: str | None
    total_credits: int
    subjects: list[CurriculumSubjectOut]


class ProgramCurriculum(BaseModel):
    program_id: UUID
    program_name: str
    school: str
    curricula: list[CurriculumPublic]
