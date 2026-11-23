// Mode démo de l'authentification (backend : AUTH_DEV_MODE=true).
// Tant que /auth/login n'existe pas (SA-28), le responsable choisit un rôle simulé, envoyé dans
// l'en-tête X-Dev-Role des appels /catalog. Dès qu'un jeton JWT est présent, il est prioritaire.
const KEY = "smartcampus_dev_role";

export const DEV_ROLES = [
  { value: "admin", label: "Administrateur (toutes les écoles)" },
  { value: "iit_manager", label: "Responsable académique IIT" },
  { value: "isb_manager", label: "Responsable académique ISB" },
  { value: "direction", label: "Direction (lecture seule)" },
] as const;

export type DevRole = (typeof DEV_ROLES)[number]["value"];

export const devRoleStore = {
  get(): DevRole {
    try {
      const v = typeof window !== "undefined" ? window.localStorage.getItem(KEY) : null;
      return (DEV_ROLES.some((r) => r.value === v) ? v : "admin") as DevRole;
    } catch { return "admin"; }
  },
  set(role: DevRole) {
    try { window.localStorage.setItem(KEY, role); } catch { /* ignoré */ }
  },
};
