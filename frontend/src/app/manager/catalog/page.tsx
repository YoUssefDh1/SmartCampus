"use client";
// Espace responsable > Catalogue : formations & programmes (SA-20) et tarifs / admission (SA-21).
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import AdmissionManager from "@/components/catalog/AdmissionManager";
import CurriculaManager from "@/components/catalog/CurriculaManager";
import PaymentPlansManager from "@/components/catalog/PaymentPlansManager";
import ProgramsManager from "@/components/catalog/ProgramsManager";
import { CatalogContext, type CatalogCtx } from "@/components/catalog/shared";
import SubjectsManager from "@/components/catalog/SubjectsManager";
import TuitionManager from "@/components/catalog/TuitionManager";
import ErrorBanner from "@/components/ErrorBanner";
import { DEV_ROLES, devRoleStore, type DevRole } from "@/lib/api/devRole";
import { ApiError } from "@/lib/api/errors";
import { catalogApi } from "@/lib/api/services";
import { tokenStore } from "@/lib/api/token";
import type { Institution, Program } from "@/types/api";

const TABS = [
  { id: "programs", label: "Formations", Component: ProgramsManager },
  { id: "curricula", label: "Programmes pédagogiques", Component: CurriculaManager },
  { id: "subjects", label: "Matières", Component: SubjectsManager },
  { id: "admission", label: "Conditions d'admission", Component: AdmissionManager },
  { id: "tuition", label: "Frais de scolarité", Component: TuitionManager },
  { id: "payment", label: "Modalités de paiement", Component: PaymentPlansManager },
] as const;

const WRITE_ROLES = ["admin", "iit_manager", "isb_manager"];

/** Rôle du jeton JWT s'il existe (SA-28), sinon rôle de démo. */
function readRole(): { role: string; fromToken: boolean } {
  const token = tokenStore.get();
  if (token) {
    try {
      const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      if (typeof payload.role === "string") return { role: payload.role, fromToken: true };
    } catch { /* jeton illisible : mode démo */ }
  }
  return { role: devRoleStore.get(), fromToken: false };
}

export default function CatalogAdminPage() {
  const [who, setWho] = useState<{ role: string; fromToken: boolean } | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("programs");
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    setWho(readRole());
    const syncTab = () => {
      const hash = window.location.hash.slice(1);
      if (TABS.some((t) => t.id === hash)) setTab(hash as (typeof TABS)[number]["id"]);
    };
    syncTab();
    window.addEventListener("hashchange", syncTab);
    return () => window.removeEventListener("hashchange", syncTab);
  }, []);

  const reloadPrograms = useCallback(() => {
    catalogApi.programs.list({ size: 100, sort: "name" })
      .then((p) => { setPrograms(p.items); setError(null); })
      .catch((e) => setError(e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e))));
  }, []);

  useEffect(() => {
    if (!who) return;
    catalogApi.institutions().then(setInstitutions).catch(() => setInstitutions([]));
    reloadPrograms();
  }, [who, reloadPrograms]);

  if (!who) return <p className="muted">Chargement…</p>;

  const ctx: CatalogCtx = {
    role: who.role, canWrite: WRITE_ROLES.includes(who.role), isAdmin: ["admin", "direction"].includes(who.role),
    institutions, programs, reloadPrograms,
  };
  const Active = TABS.find((t) => t.id === tab)!.Component;

  function changeRole(role: DevRole) {
    devRoleStore.set(role);
    setWho({ role, fromToken: false });
  }

  return (
    <CatalogContext.Provider value={ctx}>
      <Link href="/manager" className="back">← Espace responsable</Link>
      <div className="spread" style={{ marginTop: 8 }}>
        <div>
          <h1>Catalogue des formations</h1>
          <p className="muted" style={{ margin: 0 }}>
            Formations, programmes, matières, conditions d&apos;admission, tarifs et modalités de paiement.
            Seules les informations <strong>publiées et valides</strong> sont vues par les candidats et l&apos;agent IA.
          </p>
        </div>
      </div>

      {!who.fromToken && (
        <div className="devbar">
          <span className="tag">Mode démo</span>
          <label className="row">Connecté en tant que
            <select value={who.role} onChange={(e) => changeRole(e.target.value as DevRole)}>
              {DEV_ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </label>
          <span className="muted small">En attendant la connexion (SA-28) : rôle simulé via l&apos;en-tête X-Dev-Role.</span>
        </div>
      )}
      {!ctx.canWrite && <div className="banner">Consultation seule : votre rôle ne permet pas de modifier le catalogue.</div>}
      {error && <ErrorBanner error={error} onRetry={reloadPrograms} />}

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={`tab ${tab === t.id ? "tab-active" : ""}`}
                  onClick={() => { setTab(t.id); history.pushState(null, "", `#${t.id}`); }}>
            {t.label}
          </button>
        ))}
      </div>
      {/* key : tout recharger quand le rôle change */}
      <div key={`${who.role}-${tab}`}><Active /></div>
    </CatalogContext.Provider>
  );
}
