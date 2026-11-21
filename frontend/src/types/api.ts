// Types des réponses du backend (contrat défini en SA-5).
export interface ApiErrorBody {
  error: { code: string; message: string; details: unknown[]; request_id: string | null };
}

export interface Page<T> { items: T[]; total: number; page: number; size: number }

export interface HealthResponse { status: string; app: string; version: string; environment: string }

export interface Program {
  id: string; school: string; name: string; level: string; duration_years: number;
  description: string; admission: string; careers: string[]; bridges: string[];
}

export interface ChatRequest { session_id?: string; message: string }
export interface ChatSource { program_id: string; title: string; origin: string }
export interface ChatResponse {
  session_id: string; reply: string; language: string; sources: ChatSource[];
  profile_updates: Record<string, unknown>;
  next_action: "ask_question" | "explain_program" | "compare_programs" | "start_preregistration" | "handover_human";
}
