// Fonctions d'accès aux APIs, groupées par domaine (mêmes noms que le backend, SA-5).
import { request } from "./client";
import type { ChatRequest, ChatResponse, HealthResponse, Page, Program } from "@/types/api";

export const healthApi = {
  check: () => request<HealthResponse>("/health"),
};

export const programsApi = {
  list: (params?: { school?: string; level?: string; page?: number; size?: number }) =>
    request<Page<Program>>("/programs", { query: params }),
  get: (id: string) => request<Program>(`/programs/${id}`),
};

export const chatApi = {
  sendMessage: (body: ChatRequest) => request<ChatResponse>("/chat/message", { method: "POST", body }),
  sendAudio: (audio: Blob, sessionId?: string) => {
    const form = new FormData();
    form.append("audio", audio, "message.webm");
    if (sessionId) form.append("session_id", sessionId);
    return request<ChatResponse & { transcript: string }>("/chat/audio", { method: "POST", body: form });
  },
};

export const candidatesApi = {
  me: () => request<unknown>("/candidates/me"),
  list: (params?: { page?: number; size?: number }) => request<Page<unknown>>("/candidates", { query: params }),
};

export const authApi = {
  guest: () => request<{ access_token: string }>("/auth/guest", { method: "POST" }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", { method: "POST", body: { email, password } }),
};
