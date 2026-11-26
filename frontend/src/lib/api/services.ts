// Fonctions d'accès aux APIs, groupées par domaine (mêmes noms que le backend, SA-5).
import { CHAT_TIMEOUT_MS, request, type Query } from "./client";
import type {
  AdmissionRequirement, AdmissionRequirementInput, ChatRequest, ChatResponse, Curriculum, CurriculumDetail,
  ChatHistoryResponse, ChatSessionsResponse, CurriculumInput, CurriculumSubjectInput, HealthResponse, Institution,
  Page, PaymentPlan, PaymentPlanInput, Program, ProgramCurriculum, ProgramDetail, ProgramInput, PublicationStatus,
  Specialty, SpecialtyInput, Subject, SubjectInput, TuitionFee, TuitionFeeInput,
} from "@/types/api";

export const healthApi = {
  check: () => request<HealthResponse>("/health"),
};

// ---------------------------------------------------------------------------
// Catalogue public (candidats, visiteurs) : informations officielles uniquement
// ---------------------------------------------------------------------------
export interface ProgramQuery extends Query {
  q?: string; school?: string; level?: string; cycle?: string; language?: string; sort?: string;
  page?: number; size?: number;
}

export const programsApi = {
  list: (params?: ProgramQuery) => request<Page<Program>>("/programs", { query: params }),
  get: (id: string) => request<ProgramDetail>(`/programs/${id}`),
  curriculum: (id: string, academic_year?: string) =>
    request<ProgramCurriculum>(`/programs/${id}/curriculum`, { query: { academic_year } }),
};

// ---------------------------------------------------------------------------
// Gestion du catalogue (responsables, administrateur)
// ---------------------------------------------------------------------------
function crud<T, Input>(base: string) {
  return {
    list: (query?: Query) => request<Page<T>>(base, { query }),
    get: (id: string) => request<T>(`${base}/${id}`),
    create: (body: Input) => request<T>(base, { method: "POST", body }),
    update: (id: string, body: Partial<Input>) => request<T>(`${base}/${id}`, { method: "PATCH", body }),
    remove: (id: string) => request<void>(`${base}/${id}`, { method: "DELETE" }),
  };
}

function publishable<T, Input>(base: string) {
  return {
    ...crud<T, Input>(base),
    setStatus: (id: string, status: PublicationStatus) =>
      request<T>(`${base}/${id}/status`, { method: "POST", body: { status } }),
  };
}

export const catalogApi = {
  institutions: () => request<Institution[]>("/catalog/institutions"),
  programs: {
    ...crud<Program, ProgramInput>("/catalog/programs"),
    specialties: (programId: string) => request<Page<Specialty>>(`/catalog/programs/${programId}/specialties`),
    addSpecialty: (programId: string, body: SpecialtyInput) =>
      request<Specialty>(`/catalog/programs/${programId}/specialties`, { method: "POST", body }),
  },
  specialties: crud<Specialty, SpecialtyInput>("/catalog/specialties"),
  subjects: crud<Subject, SubjectInput>("/catalog/subjects"),
  curricula: {
    ...crud<Curriculum, CurriculumInput>("/catalog/curricula"),
    detail: (id: string) => request<CurriculumDetail>(`/catalog/curricula/${id}`),
    duplicate: (id: string, body: { academic_year: string; version?: number | null; is_active: boolean }) =>
      request<CurriculumDetail>(`/catalog/curricula/${id}/duplicate`, { method: "POST", body }),
    addSubject: (id: string, body: CurriculumSubjectInput) =>
      request<CurriculumDetail>(`/catalog/curricula/${id}/subjects`, { method: "POST", body }),
    updateSubject: (id: string, itemId: string, body: Partial<CurriculumSubjectInput>) =>
      request<CurriculumDetail>(`/catalog/curricula/${id}/subjects/${itemId}`, { method: "PATCH", body }),
    removeSubject: (id: string, itemId: string) =>
      request<CurriculumDetail>(`/catalog/curricula/${id}/subjects/${itemId}`, { method: "DELETE" }),
  },
  admissionRequirements: publishable<AdmissionRequirement, AdmissionRequirementInput>("/catalog/admission-requirements"),
  tuitionFees: publishable<TuitionFee, TuitionFeeInput>("/catalog/tuition-fees"),
  paymentPlans: publishable<PaymentPlan, PaymentPlanInput>("/catalog/payment-plans"),
};

// ---------------------------------------------------------------------------
export const chatApi = {
  sessions: () => request<ChatSessionsResponse>("/chat/sessions"),
  history: (sessionId: string) =>
    request<ChatHistoryResponse>(`/chat/sessions/${encodeURIComponent(sessionId)}/history`),
  sendMessage: (body: ChatRequest) =>
    request<ChatResponse>("/chat/message", { method: "POST", body, timeoutMs: CHAT_TIMEOUT_MS }),
  sendAudio: (audio: Blob, sessionId?: string) => {
    const form = new FormData();
    form.append("audio", audio, "message.webm");
    if (sessionId) form.append("session_id", sessionId);
    return request<ChatResponse & { transcript: string }>("/chat/audio", {
      method: "POST",
      body: form,
      timeoutMs: CHAT_TIMEOUT_MS,
    });
  },
};

export const candidatesApi = {
  me: () => request<unknown>("/candidates/me"),
  list: (params?: { page?: number; size?: number }) => request<Page<unknown>>("/candidates", { query: params }),
};

export const authApi = {
  guest: () => request<{
    access_token: string;
    token_type: string;
    role: string;
    session_id: string;
    expires_at: string;
  }>("/auth/guest", { method: "POST" }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", { method: "POST", body: { email, password } }),
};
