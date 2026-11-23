"use client";
// Briques communes des écrans de gestion du catalogue.
import { createContext, useContext, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/ui/Modal";
import { ApiError } from "@/lib/api/errors";
import { academicYears, STATUSES, VISIBILITIES } from "@/lib/catalog";
import type { Institution, Program, PublicationStatus, Visibility } from "@/types/api";

export interface CatalogCtx {
  role: string;
  canWrite: boolean;
  isAdmin: boolean;          // admin / direction : voient toutes les écoles
  institutions: Institution[];
  programs: Program[];       // formations accessibles (listes déroulantes)
  reloadPrograms: () => void;
}

export const CatalogContext = createContext<CatalogCtx | null>(null);

export function useCatalog(): CatalogCtx {
  const ctx = useContext(CatalogContext);
  if (!ctx) throw new Error("useCatalog doit être utilisé dans CatalogContext");
  return ctx;
}

// --- Formulaires -------------------------------------------------------------------------
export function Field({ label, hint, full, children }: {
  label: string; hint?: string; full?: boolean; children: React.ReactNode;
}) {
  return (
    <label className={`field ${full ? "full" : ""}`}>
      <span>{label}</span>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </label>
  );
}

/** Exécute un appel API et garde l'erreur à afficher dans le formulaire. */
export function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  async function run(fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true); setError(null);
    try { await fn(); return true; }
    catch (e) { setError(e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e))); return false; }
    finally { setBusy(false); }
  }
  return { busy, error, setError, run };
}

export function FormModal({ title, onClose, onSubmit, busy, error, wide, children, submitLabel = "Enregistrer" }: {
  title: string; onClose: () => void; onSubmit: () => void; busy: boolean; error: ApiError | null;
  wide?: boolean; children: React.ReactNode; submitLabel?: string;
}) {
  return (
    <Modal title={title} onClose={onClose} wide={wide}>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
        {error && <ErrorBanner error={error} />}
        <div className="form-grid">{children}</div>
        <div className="form-actions">
          <button type="button" className="btn btn-light" onClick={onClose}>Annuler</button>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Enregistrement…" : submitLabel}</button>
        </div>
      </form>
    </Modal>
  );
}

export function ProgramSelect({ value, onChange, allLabel, required, disabled, onlyActive }: {
  value: string; onChange: (id: string) => void; allLabel?: string; required?: boolean; disabled?: boolean;
  onlyActive?: boolean;
}) {
  const { programs, isAdmin } = useCatalog();
  const list = onlyActive ? programs.filter((p) => p.is_active || p.id === value) : programs;
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} required={required} disabled={disabled}
            aria-label="Formation">
      {allLabel !== undefined ? <option value="">{allLabel}</option> : <option value="" disabled>Choisir une formation…</option>}
      {list.map((p) => (
        <option key={p.id} value={p.id}>{isAdmin ? `${p.school} · ` : ""}{p.name}{p.is_active ? "" : " (inactive)"}</option>
      ))}
    </select>
  );
}

export function YearSelect({ value, onChange, allLabel, required }: {
  value: string; onChange: (v: string) => void; allLabel?: string; required?: boolean;
}) {
  const years = academicYears(5);
  if (value && !years.includes(value)) years.push(value);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} required={required} aria-label="Année universitaire">
      {allLabel !== undefined && <option value="">{allLabel}</option>}
      {years.map((y) => <option key={y} value={y}>{y}</option>)}
    </select>
  );
}

export function VisibilitySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label="Statut">
      <option value="">Tous les statuts</option>
      {(Object.keys(VISIBILITIES) as Visibility[]).map((v) => <option key={v} value={v}>{VISIBILITIES[v].label}</option>)}
    </select>
  );
}

/** Période de validité + raccourci « toute l'année universitaire ». */
export function ValidityFields({ from, until, academicYear, onChange }: {
  from: string; until: string; academicYear?: string; onChange: (from: string, until: string) => void;
}) {
  const start = academicYear ? Number(academicYear.slice(0, 4)) : null;
  return (
    <>
      <Field label="Valide à partir du" hint="Vide = immédiatement">
        <input type="date" value={from} onChange={(e) => onChange(e.target.value, until)} />
      </Field>
      <Field label="Valide jusqu'au" hint="Vide = sans date de fin">
        <input type="date" value={until} min={from || undefined} onChange={(e) => onChange(from, e.target.value)} />
      </Field>
      {start && (
        <div className="full row">
          <button type="button" className="btn btn-ghost btn-sm"
                  onClick={() => onChange(`${start}-09-01`, `${start + 1}-08-31`)}>
            Valable toute l&apos;année {academicYear} (01/09 → 31/08)
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => onChange("", "")}>Sans limite</button>
        </div>
      )}
    </>
  );
}

// --- Publication ---------------------------------------------------------------------------
export function PublicationActions({ status, onChange, disabled }: {
  status: PublicationStatus; onChange: (s: PublicationStatus) => void; disabled?: boolean;
}) {
  const actions: { to: PublicationStatus; label: string; title: string }[] =
    status === "draft" ? [{ to: "published", label: "Publier", title: "Rendre officiel (visible pendant la période de validité)" },
                          { to: "archived", label: "Archiver", title: "Conserver pour l'historique" }]
    : status === "published" ? [{ to: "draft", label: "Dépublier", title: "Repasser en brouillon (invisible)" },
                                { to: "archived", label: "Archiver", title: "Conserver pour l'historique" }]
    : [{ to: "draft", label: "Restaurer", title: "Repasser en brouillon pour modifier" }];
  return (
    <>
      {actions.map((a) => (
        <button key={a.to} className="btn btn-ghost btn-sm" title={a.title} disabled={disabled} onClick={() => onChange(a.to)}>
          {a.label}
        </button>
      ))}
    </>
  );
}

export const STATUS_OPTIONS = Object.entries(STATUSES);

export function confirmDelete(what: string): boolean {
  return window.confirm(`Supprimer ${what} ? Cette action est définitive.`);
}
