const KEY = "smartcampus_conversation_id";
let memorySessionId: string | null = null;

export const chatSessionStore = {
  get(): string | null {
    if (memorySessionId) return memorySessionId;
    try { return typeof window !== "undefined" ? window.localStorage.getItem(KEY) : null; } catch { return null; }
  },
  set(sessionId: string) {
    memorySessionId = sessionId;
    try { window.localStorage.setItem(KEY, sessionId); } catch { /* storage can be unavailable */ }
  },
  clear() {
    memorySessionId = null;
    try { window.localStorage.removeItem(KEY); } catch { /* storage can be unavailable */ }
  },
};
