"""Schémas du catalogue (Membre 3 - SA-20 / SA-21).

Vocabulaire aligné sur schema.sql :
  program = formation, specialty = spécialité, curriculum = programme pédagogique,
  subject = matière, admission_requirement = condition d'admission / prérequis,
  tuition_fee = frais de scolarité, payment_plan = modalité de paiement (migration 002).

Entrées (*Create / *Update) : champs inconnus refusés, textes nettoyés.
PATCH (*Update) : seuls les champs envoyés sont modifiés.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import (AfterValidator, BaseModel, ConfigDict, Field, computed_field, field_validator,
                      model_validator)

# ---------------------------------------------------------------------------
# Vocabulaire (identique aux CHECK de la base)
# ---------------------------------------------------------------------------
PublicationStatus = Literal["draft", "published", "archived"]
# Ce que voit réellement le candidat : en ligne, programmé (pas encore valide), expiré, brouillon, archivé.
Visibility = Literal["visible", "scheduled", "expired", "draft", "archived"]
Cycle = Literal["preparatory", "engineering", "bachelor", "master", "other"]
RequirementCategory = Literal["admission", "prerequisite"]
RequirementKind = Literal["bac_series", "minimum_average", "prior_diploma", "entrance_exam", "document", "skill", "other"]
FeeType = Literal["application", "registration", "tuition", "other"]
PaymentMethod = Literal["cash", "bank_transfer", "check", "card", "online"]

CYCLE_LABELS: dict[str, str] = {
    "preparatory": "Préparatoire",
    "engineering": "Ingénierie",
    "bachelor": "Licence",
    "master": "Master",
    "other": "Autre",
}


def _check_academic_year(value: str | None) -> str | None:
    if value is not None:
        start, end = (int(part) for part in value.split("-"))
        if end != start + 1:
            raise ValueError("L'année universitaire doit se suivre, par exemple 2026-2027.")
    return value


AcademicYear = Annotated[str, Field(pattern=r"^\d{4}-\d{4}$", examples=["2026-2027"]),
                         AfterValidator(_check_academic_year)]
Code = Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_.\-]+$", examples=["ING-INFO"]),
                 AfterValidator(lambda v: v.upper())]
Grade20 = Annotated[Decimal, Field(ge=0, le=20, max_digits=4, decimal_places=2)]
Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2, examples=["6500.00"])]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$", examples=["TND"])]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PatchModel(InputModel):
    """PATCH : un champ obligatoire en base peut être omis, mais pas envoyé à null."""

    not_nullable: ClassVar[set[str]] = set()

    @model_validator(mode="after")
    def _no_null_on_required(self):
        bad = [f for f in self.model_fields_set & self.not_nullable if getattr(self, f) is None]
        if bad:
            raise ValueError(f"Ces champs ne peuvent pas être vides : {', '.join(sorted(bad))}.")
        return self

    def changes(self) -> dict:
        return self.model_dump(exclude_unset=True)


class ValidityPeriod(BaseModel):
    """Période de validité (bornes incluses, NULL = ouverte)."""

    valid_from: date | None = Field(None, description="Premier jour de validité (inclus)")
    valid_until: date | None = Field(None, description="Dernier jour de validité (inclus)")

    @model_validator(mode="after")
    def _check_period(self):
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("La date de fin de validité doit être postérieure à la date de début.")
        return self


class PublicationInfo(BaseModel):
    status: PublicationStatus
    visibility: Visibility
    valid_from: date | None
    valid_until: date | None
    published_at: datetime | None
    published_by_id: UUID | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_currently_valid(self) -> bool:
        """True = information officielle visible par les candidats et l'agent IA aujourd'hui."""
        return self.visibility == "visible"


class PublicationStatusChange(InputModel):
    status: PublicationStatus = Field(description="draft = brouillon, published = publier, archived = archiver")


class ProgramRef(BaseModel):
    """Rappel de la formation sur les éléments qui en dépendent (listes du responsable)."""

    program_id: UUID
    program_code: str
    program_name: str
    school: str


# ---------------------------------------------------------------------------
# Écoles
# ---------------------------------------------------------------------------
class InstitutionOut(BaseModel):
    id: UUID
    code: str
    name: str


# ---------------------------------------------------------------------------
# Formations (program)
# ---------------------------------------------------------------------------
def _languages(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for v in values:
        v = v.strip().lower()
        if not 2 <= len(v) <= 10:
            raise ValueError("Langue : utiliser un code court (fr, en, ar).")
        if v not in cleaned:
            cleaned.append(v)
    return cleaned


Languages = Annotated[list[str], AfterValidator(_languages), Field(examples=[["fr", "en"]])]


class ProgramCreate(InputModel):
    institution_id: UUID | None = Field(
        None, description="École. Obligatoire pour l'administrateur ; imposée (sa propre école) pour un responsable.")
    code: Code
    name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    cycle: Cycle
    duration_years: int | None = Field(None, ge=1, le=10)
    degree: str | None = Field(None, max_length=150)
    capacity: int | None = Field(None, ge=0)
    teaching_languages: Languages = Field(default_factory=list)
    career_outcomes: str | None = None
    is_active: bool = True


class ProgramUpdate(PatchModel):
    not_nullable: ClassVar[set[str]] = {"institution_id", "code", "name", "cycle", "teaching_languages", "is_active"}

    institution_id: UUID | None = Field(None, description="Administrateur uniquement")
    code: Code | None = None
    name: str | None = Field(None, min_length=2, max_length=200)
    description: str | None = None
    cycle: Cycle | None = None
    duration_years: int | None = Field(None, ge=1, le=10)
    degree: str | None = Field(None, max_length=150)
    capacity: int | None = Field(None, ge=0)
    teaching_languages: Languages | None = None
    career_outcomes: str | None = None
    is_active: bool | None = None


class ProgramOut(BaseModel):
    id: UUID
    institution_id: UUID
    school: str = Field(description="Code de l'école (IIT, ISB)")
    institution_name: str
    code: str
    name: str
    description: str | None
    cycle: Cycle
    duration_years: int | None
    degree: str | None
    capacity: int | None
    teaching_languages: list[str]
    career_outcomes: str | None
    is_active: bool
    specialties_count: int = 0
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def level(self) -> str:
        """Libellé du cycle (Préparatoire, Ingénierie, Licence, Master)."""
        return CYCLE_LABELS[self.cycle]


# ---------------------------------------------------------------------------
# Spécialités (specialty)
# ---------------------------------------------------------------------------
class SpecialtyCreate(InputModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    is_active: bool = True


class SpecialtyUpdate(PatchModel):
    not_nullable: ClassVar[set[str]] = {"name", "is_active"}

    name: str | None = Field(None, min_length=2, max_length=150)
    description: str | None = None
    is_active: bool | None = None


class SpecialtyOut(ProgramRef):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    curricula_count: int = 0
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Matières (subject)
# ---------------------------------------------------------------------------
class SubjectCreate(InputModel):
    code: Code
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None


class SubjectUpdate(PatchModel):
    not_nullable: ClassVar[set[str]] = {"code", "name"}

    code: Code | None = None
    name: str | None = Field(None, min_length=2, max_length=150)
    description: str | None = None


class SubjectOut(BaseModel):
    id: UUID
    code: str
    name: str
    description: str | None
    usage_count: int = Field(0, description="Nombre de programmes pédagogiques qui utilisent la matière")
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Programmes pédagogiques (curriculum) et leurs matières (curriculum_subject)
# ---------------------------------------------------------------------------
class CurriculumSubjectCreate(InputModel):
    subject_id: UUID
    study_year: int = Field(ge=1, le=8, description="Année d'étude (1..n)")
    semester: int = Field(ge=1, le=16, description="Semestre global dans le programme (1..n)")
    coefficient: Decimal | None = Field(None, ge=0, max_digits=4, decimal_places=2)
    credits: int | None = Field(None, ge=0, le=60)
    is_mandatory: bool = True


class CurriculumSubjectUpdate(PatchModel):
    not_nullable: ClassVar[set[str]] = {"subject_id", "study_year", "semester", "is_mandatory"}

    subject_id: UUID | None = None
    study_year: int | None = Field(None, ge=1, le=8)
    semester: int | None = Field(None, ge=1, le=16)
    coefficient: Decimal | None = Field(None, ge=0, max_digits=4, decimal_places=2)
    credits: int | None = Field(None, ge=0, le=60)
    is_mandatory: bool | None = None


class CurriculumSubjectOut(BaseModel):
    id: UUID
    curriculum_id: UUID
    subject_id: UUID
    subject_code: str
    subject_name: str
    study_year: int
    semester: int
    coefficient: float | None
    credits: int | None
    is_mandatory: bool


class CurriculumCreate(InputModel):
    program_id: UUID
    specialty_id: UUID | None = Field(None, description="Vide = programme commun à toute la formation")
    academic_year: AcademicYear
    version: int = Field(1, ge=1)
    description: str | None = None
    is_active: bool = Field(True, description="Activer désactive automatiquement les autres versions de la même année")


class CurriculumUpdate(PatchModel):
    not_nullable: ClassVar[set[str]] = {"academic_year", "version", "is_active"}

    specialty_id: UUID | None = None
    academic_year: AcademicYear | None = None
    version: int | None = Field(None, ge=1)
    description: str | None = None
    is_active: bool | None = None


class CurriculumDuplicate(InputModel):
    academic_year: AcademicYear
    version: int | None = Field(None, ge=1, description="Par défaut : prochaine version libre pour cette année")
    is_active: bool = False


class CurriculumOut(ProgramRef):
    id: UUID
    specialty_id: UUID | None
    specialty_name: str | None
    academic_year: str
    version: int
    description: str | None
    is_active: bool
    subjects_count: int = 0
    total_credits: int = 0
    created_at: datetime
    updated_at: datetime


class CurriculumDetail(CurriculumOut):
    subjects: list[CurriculumSubjectOut] = []


# ---------------------------------------------------------------------------
# Conditions d'admission (admission_requirement)
# ---------------------------------------------------------------------------
class AdmissionRequirementCreate(InputModel, ValidityPeriod):
    program_id: UUID
    category: RequirementCategory = "admission"
    kind: RequirementKind
    description: str = Field(min_length=3)
    min_average: Grade20 | None = Field(None, description="Obligatoire si kind = minimum_average")
    accepted_bac_series: list[str] | None = Field(None, examples=[["Mathématiques", "Sciences techniques"]])
    required_program_id: UUID | None = Field(None, description="Formation exigée (ex. cycle préparatoire)")
    academic_year: AcademicYear | None = Field(None, description="Vide = toutes les années")
    is_mandatory: bool = True
    position: int = Field(0, ge=0, le=1000)

    @model_validator(mode="after")
    def _check_kind(self):
        if self.kind == "minimum_average" and self.min_average is None:
            raise ValueError("Une condition « moyenne minimale » exige la valeur min_average.")
        return self


class AdmissionRequirementUpdate(PatchModel, ValidityPeriod):
    not_nullable: ClassVar[set[str]] = {"category", "kind", "description", "is_mandatory", "position"}

    category: RequirementCategory | None = None
    kind: RequirementKind | None = None
    description: str | None = Field(None, min_length=3)
    min_average: Grade20 | None = None
    accepted_bac_series: list[str] | None = None
    required_program_id: UUID | None = None
    academic_year: AcademicYear | None = None
    is_mandatory: bool | None = None
    position: int | None = Field(None, ge=0, le=1000)


class AdmissionRequirementPublic(BaseModel):
    id: UUID
    category: RequirementCategory
    kind: RequirementKind
    description: str
    min_average: float | None
    accepted_bac_series: list[str] | None
    required_program_id: UUID | None
    required_program_name: str | None
    academic_year: str | None
    is_mandatory: bool
    position: int
    valid_from: date | None
    valid_until: date | None


class AdmissionRequirementOut(ProgramRef, PublicationInfo):
    id: UUID
    category: RequirementCategory
    kind: RequirementKind
    description: str
    min_average: float | None
    accepted_bac_series: list[str] | None
    required_program_id: UUID | None
    required_program_name: str | None
    academic_year: str | None
    is_mandatory: bool
    position: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Frais de scolarité (tuition_fee)
# ---------------------------------------------------------------------------
class TuitionFeeCreate(InputModel, ValidityPeriod):
    program_id: UUID
    academic_year: AcademicYear
    study_year: int | None = Field(None, ge=1, le=8, description="Vide = toutes les années d'étude")
    fee_type: FeeType
    amount: Money
    currency: Currency = "TND"
    description: str | None = None


class TuitionFeeUpdate(PatchModel, ValidityPeriod):
    not_nullable: ClassVar[set[str]] = {"academic_year", "fee_type", "amount", "currency"}

    academic_year: AcademicYear | None = None
    study_year: int | None = Field(None, ge=1, le=8)
    fee_type: FeeType | None = None
    amount: Money | None = None
    currency: Currency | None = None
    description: str | None = None


class TuitionFeePublic(BaseModel):
    id: UUID
    academic_year: str
    study_year: int | None
    fee_type: FeeType
    amount: float
    currency: str
    description: str | None
    valid_from: date | None
    valid_until: date | None


class TuitionFeeOut(ProgramRef, PublicationInfo):
    id: UUID
    academic_year: str
    study_year: int | None
    fee_type: FeeType
    amount: float
    currency: str
    description: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Modalités de paiement (payment_plan + payment_installment)
# ---------------------------------------------------------------------------
class InstallmentIn(InputModel):
    label: str = Field(min_length=1, max_length=150, examples=["1re tranche"])
    due_date: date | None = None
    due_description: str | None = Field(None, max_length=150, examples=["À l'inscription"])
    percentage: Decimal | None = Field(None, gt=0, le=100, max_digits=5, decimal_places=2)
    amount: Money | None = None

    @model_validator(mode="after")
    def _percentage_or_amount(self):
        if self.percentage is None and self.amount is None:
            raise ValueError("Chaque échéance doit avoir un pourcentage ou un montant.")
        return self


def _check_installments(items: list[InstallmentIn] | None) -> list[InstallmentIn] | None:
    if items and all(i.percentage is not None for i in items):
        total = sum(i.percentage for i in items)  # type: ignore[misc]
        if total != 100:
            raise ValueError(f"La somme des pourcentages des échéances doit faire 100 % (actuellement {total} %).")
    return items


Installments = Annotated[list[InstallmentIn], Field(min_length=1, max_length=12), AfterValidator(_check_installments)]


class InstallmentOut(BaseModel):
    id: UUID
    position: int
    label: str
    due_date: date | None
    due_description: str | None
    percentage: float | None
    amount: float | None


def _unique_methods(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


Methods = Annotated[list[PaymentMethod], AfterValidator(_unique_methods)]


class PaymentPlanCreate(InputModel, ValidityPeriod):
    program_id: UUID
    academic_year: AcademicYear
    name: str = Field(min_length=2, max_length=150, examples=["Paiement en 3 tranches"])
    description: str | None = None
    payment_methods: Methods = Field(default_factory=list)
    discount_percent: Percent | None = None
    currency: Currency = "TND"
    conditions: str | None = None
    position: int = Field(0, ge=0, le=1000)
    installments: Installments


class PaymentPlanUpdate(PatchModel, ValidityPeriod):
    not_nullable: ClassVar[set[str]] = {"academic_year", "name", "payment_methods", "currency", "position",
                                        "installments"}

    academic_year: AcademicYear | None = None
    name: str | None = Field(None, min_length=2, max_length=150)
    description: str | None = None
    payment_methods: Methods | None = None
    discount_percent: Percent | None = None
    currency: Currency | None = None
    conditions: str | None = None
    position: int | None = Field(None, ge=0, le=1000)
    installments: Installments | None = Field(None, description="Si fourni, remplace toutes les échéances")


class PaymentPlanPublic(BaseModel):
    id: UUID
    academic_year: str
    name: str
    description: str | None
    payment_methods: list[PaymentMethod]
    discount_percent: float | None
    currency: str
    conditions: str | None
    position: int
    valid_from: date | None
    valid_until: date | None
    installments: list[InstallmentOut]


class PaymentPlanOut(ProgramRef, PublicationInfo):
    id: UUID
    academic_year: str
    name: str
    description: str | None
    payment_methods: list[PaymentMethod]
    discount_percent: float | None
    currency: str
    conditions: str | None
    position: int
    installments: list[InstallmentOut]
    created_at: datetime
    updated_at: datetime

    @field_validator("installments", mode="before")
    @classmethod
    def _none_to_list(cls, v):
        return v or []
