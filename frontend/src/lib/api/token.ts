// Stockage du jeton JWT (visiteur ou connecté). Protégé : le stockage peut être indisponible.
const KEY = "smartcampus_token";
let memoryToken: string | null = null;

export const tokenStore = {
  get(): string | null {
    if (memoryToken) return memoryToken;
    try { return typeof window !== "undefined" ? window.localStorage.getItem(KEY) : null; } catch { return null; }
  },
  set(token: string) {
    memoryToken = token;
    try { window.localStorage.setItem(KEY, token); } catch { /* ignoré */ }
  },
  clear() {
    memoryToken = null;
    try { window.localStorage.removeItem(KEY); } catch { /* ignoré */ }
  },
};
