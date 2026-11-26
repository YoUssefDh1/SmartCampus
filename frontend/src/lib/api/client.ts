// Client HTTP unique vers le backend : base URL, jeton JWT, timeout, et conversion des erreurs en ApiError.
import { devRoleStore } from "./devRole";
import { ApiError } from "./errors";
import { tokenStore } from "./token";
import type { ApiErrorBody } from "@/types/api";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const TIMEOUT_MS = 15000;
const DEFAULT_CHAT_TIMEOUT_MS = 130_000;
export const CHAT_TIMEOUT_MS = (() => {
  const configured = process.env.NEXT_PUBLIC_CHAT_TIMEOUT_MS;
  if (configured === undefined) return DEFAULT_CHAT_TIMEOUT_MS;

  const timeout = Number(configured);
  if (!Number.isSafeInteger(timeout) || timeout <= 0) {
    throw new Error("NEXT_PUBLIC_CHAT_TIMEOUT_MS must be a positive integer.");
  }
  return timeout;
})();

export type Query = Record<string, string | number | boolean | undefined | null>;
interface Options { method?: string; body?: unknown; query?: Query; signal?: AbortSignal; timeoutMs?: number }

// Appelé quand le backend répond 401 (ex. rediriger vers la connexion). Défini par l'application.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

export async function request<T>(path: string, opts: Options = {}): Promise<T> {
  const url = new URL(API_URL + path);
  Object.entries(opts.query ?? {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v)); });

  const headers: Record<string, string> = { Accept: "application/json" };
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
  if (opts.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  else if (path.startsWith("/catalog")) headers["X-Dev-Role"] = devRoleStore.get(); // mode démo (voir devRole.ts)

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? TIMEOUT_MS);
  opts.signal?.addEventListener("abort", () => controller.abort());

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method: opts.method ?? "GET",
      headers,
      body: opts.body === undefined ? undefined : isForm ? (opts.body as FormData) : JSON.stringify(opts.body),
      signal: controller.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw new ApiError(0, "TIMEOUT", "Délai dépassé");
    throw new ApiError(0, "NETWORK_ERROR", "Serveur injoignable");
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 204) return undefined as T;

  let data: unknown = null;
  try { data = await res.json(); } catch { /* corps vide ou non JSON */ }

  if (!res.ok) {
    const err = (data as ApiErrorBody | null)?.error;
    const apiError = new ApiError(res.status, err?.code ?? "HTTP_ERROR", err?.message ?? res.statusText, err?.details ?? [], err?.request_id ?? null);
    if (res.status === 401) { tokenStore.clear(); onUnauthorized?.(); }
    throw apiError;
  }
  return data as T;
}
