// Types des réponses du backend (contrat défini en SA-5 ; catalogue : SA-20 / SA-21).
export interface ApiErrorBody {
  error: { code: string; message: string; details: unknown[]; request_id: string | null };
}

export interface Page<T> { items: T[]; total: number; page: number; size: number }

export interface HealthResponse { status: string; app: string; version: string; environment: string }

export interface ChatRequest { session_id?: string; message: string }
export interface ChatSource { source_id: string; title: string; origin: string; page?: number | null }
export interface ChatResponse {
  session_id: string; reply: string; language: string; sources: ChatSource[];
  profile_updates: Record<string, unknown>;
  next_action: "ask_question" | "explain_program" | "compare_programs" | "start_preregistration" | "handover_human";
}
export interface ChatSessionSummary { id: string; status: string }
export interface ChatHistoryMessage { id: string; role: "user" | "assistant" | "system"; content: string }
export interface ChatHistoryResponse { id: string; messages: ChatHistoryMessage[] }
export interface ChatSessionsResponse { items: ChatSessionSummary[]; total: number }

// ---------------------------------------------------------------------------
// Catalogue : vocabulaire identique à schema.sql + migration 002
// ---------------------------------------------------------------------------
export type Cycle = "preparatory" | "engineering" | "bachelor" | "master" | "other";
export type PublicationStatus = "draft" | "published" | "archived";
export type Visibility = "visible" | "scheduled" | "expired" | "draft" | "archived";
export type RequirementCategory = "admission" | "prerequisite";
export type RequirementKind =
  | "bac_series" | "minimum_average" | "prior_diploma" | "entrance_exam" | "document" | "skill" | "other";
export type FeeType = "application" | "registration" | "tuition" | "other";
export type PaymentMethod = "cash" | "bank_transfer" | "check" | "card" | "online";

export interface Institution { id: string; code: string; name: string }

export interface Program {
  id: string; institution_id: string; school: string; institution_name: string;
  code: string; name: string; description: string | null; cycle: Cycle; level: string;
  duration_years: number | null; degree: string | null; capacity: number | null;
  teaching_languages: string[]; career_outcomes: string | null; is_active: boolean;
  specialties_count: number; created_at: string; updated_at: string;
  tuition_from?: number | null; tuition_currency?: string | null;
}

export interface ProgramInput {
  institution_id?: string | null; code: string; name: string; description: string | null; cycle: Cycle;
  duration_years: number | null; degree: string | null; capacity: number | null;
  teaching_languages: string[]; career_outcomes: string | null; is_active: boolean;
}

/** Rappel de la formation sur les éléments qui en dépendent. */
export interface ProgramRef { program_id: string; program_code: string; program_name: string; school: string }

export interface PublicationInfo {
  status: PublicationStatus; visibility: Visibility; is_currently_valid: boolean;
  valid_from: string | null; valid_until: string | null; published_at: string | null; published_by_id: string | null;
}

export interface Specialty extends ProgramRef {
  id: string; name: string; description: string | null; is_active: boolean; curricula_count: number;
  created_at: string; updated_at: string;
}
export interface SpecialtyInput { name: string; description: string | null; is_active: boolean }
export interface SpecialtyPublic { id: string; name: string; description: string | null }

export interface Subject {
  id: string; code: string; name: string; description: string | null; usage_count: number;
  created_at: string; updated_at: string;
}
export interface SubjectInput { code: string; name: string; description: string | null }

export interface CurriculumSubject {
  id: string; curriculum_id: string; subject_id: string; subject_code: string; subject_name: string;
  study_year: number; semester: number; coefficient: number | null; credits: number | null; is_mandatory: boolean;
}
export interface CurriculumSubjectInput {
  subject_id: string; study_year: number; semester: number; coefficient: number | null; credits: number | null;
  is_mandatory: boolean;
}
export interface Curriculum extends ProgramRef {
  id: string; specialty_id: string | null; specialty_name: string | null; academic_year: string; version: number;
  description: string | null; is_active: boolean; subjects_count: number; total_credits: number;
  created_at: string; updated_at: string;
}
export interface CurriculumDetail extends Curriculum { subjects: CurriculumSubject[] }
export interface CurriculumInput {
  program_id?: string; specialty_id: string | null; academic_year: string; version: number;
  description: string | null; is_active: boolean;
}

export interface AdmissionRequirementPublic {
  id: string; category: RequirementCategory; kind: RequirementKind; description: string;
  min_average: number | null; accepted_bac_series: string[] | null; required_program_id: string | null;
  required_program_name: string | null; academic_year: string | null; is_mandatory: boolean; position: number;
  valid_from: string | null; valid_until: string | null;
}
export interface AdmissionRequirement extends AdmissionRequirementPublic, ProgramRef, PublicationInfo {
  created_at: string; updated_at: string;
}
export interface AdmissionRequirementInput {
  program_id?: string; category: RequirementCategory; kind: RequirementKind; description: string;
  min_average: number | null; accepted_bac_series: string[] | null; required_program_id: string | null;
  academic_year: string | null; is_mandatory: boolean; position: number;
  valid_from: string | null; valid_until: string | null;
}

export interface TuitionFeePublic {
  id: string; academic_year: string; study_year: number | null; fee_type: FeeType; amount: number;
  currency: string; description: string | null; valid_from: string | null; valid_until: string | null;
}
export interface TuitionFee extends TuitionFeePublic, ProgramRef, PublicationInfo { created_at: string; updated_at: string }
export interface TuitionFeeInput {
  program_id?: string; academic_year: string; study_year: number | null; fee_type: FeeType; amount: number;
  currency: string; description: string | null; valid_from: string | null; valid_until: string | null;
}

export interface Installment {
  id?: string; position?: number; label: string; due_date: string | null; due_description: string | null;
  percentage: number | null; amount: number | null;
}
export interface PaymentPlanPublic {
  id: string; academic_year: string; name: string; description: string | null; payment_methods: PaymentMethod[];
  discount_percent: number | null; currency: string; conditions: string | null; position: number;
  valid_from: string | null; valid_until: string | null; installments: Installment[];
}
export interface PaymentPlan extends PaymentPlanPublic, ProgramRef, PublicationInfo { created_at: string; updated_at: string }
export interface PaymentPlanInput {
  program_id?: string; academic_year: string; name: string; description: string | null;
  payment_methods: PaymentMethod[]; discount_percent: number | null; currency: string; conditions: string | null;
  position: number; valid_from: string | null; valid_until: string | null; installments: Installment[];
}

export interface ProgramDetail extends Program {
  specialties: SpecialtyPublic[];
  admission_requirements: AdmissionRequirementPublic[];
  tuition_fees: TuitionFeePublic[];
  payment_plans: PaymentPlanPublic[];
}
export interface ProgramCurriculum {
  program_id: string; program_name: string; school: string;
  curricula: (Omit<Curriculum, keyof ProgramRef | "is_active" | "subjects_count" | "created_at" | "updated_at"> & {
    subjects: CurriculumSubject[];
  })[];
}
