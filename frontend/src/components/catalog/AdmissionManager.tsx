"use client";
// Conditions d'admission et prérequis : CRUD + publication + période de validité.
import { useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Pagination from "@/components/ui/Pagination";
import StatusBadge from "@/components/ui/StatusBadge";
import { catalogApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import { blankToNull, REQUIREMENT_CATEGORIES, REQUIREMENT_KINDS, str, toNumber, validity } from "@/lib/catalog";
import { useDebounced } from "@/lib/useDebounced";
import type { AdmissionRequirement, PublicationStatus, RequirementCategory, RequirementKind } from "@/types/api";
import {
  confirmDelete, Field, FormModal, ProgramSelect, PublicationActions, useCatalog, useSubmit, ValidityFields,
  VisibilitySelect, YearSelect,
} from "./shared";

const SIZE = 25;

export default function AdmissionManager() {
  const { canWrite } = useCatalog();
  const [programId, setProgramId] = useState("");
  const [category, setCategory] = useState("");
  const [kind, setKind] = useState("");
  const [visibility, setVisibility] = useState("");
  const [year, setYear] = useState("");
  const [text, setText] = useState("");
  const q = useDebounced(text);
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<AdmissionRequirement | "new" | null>(null);
  const action = useSubmit();
  const { data, error, loading, reload } = useApi(
    () => catalogApi.admissionRequirements.list({ program_id: programId, category, kind, visibility, academic_year: year, q, page, size: SIZE }),
    [programId, category, kind, visibility, year, q, page]);
  const f = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1); };

  async function setStatus(r: AdmissionRequirement, s: PublicationStatus) {
    if (await action.run(() => catalogApi.admissionRequirements.setStatus(r.id, s))) reload();
  }
  async function remove(r: AdmissionRequirement) {
    if (confirmDelete("cette condition d'admission") && await action.run(() => catalogApi.admissionRequirements.remove(r.id))) reload();
  }

  return (
    <>
      <div className="filters">
        <input className="search" type="search" placeholder="Rechercher…" value={text} onChange={(e) => f(setText)(e.target.value)} />
        <ProgramSelect value={programId} onChange={f(setProgramId)} allLabel="Toutes les formations" />
        <select value={category} onChange={(e) => f(setCategory)(e.target.value)} aria-label="Catégorie">
          <option value="">Admission et prérequis</option>
          {Object.entries(REQUIREMENT_CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={kind} onChange={(e) => f(setKind)(e.target.value)} aria-label="Type">
          <option value="">Tous les types</option>
          {Object.entries(REQUIREMENT_KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <YearSelect value={year} onChange={f(setYear)} allLabel="Toutes les années" />
        <VisibilitySelect value={visibility} onChange={f(setVisibility)} />
        {canWrite && <button className="btn" onClick={() => setEditing("new")}>+ Nouvelle condition</button>}
      </div>
      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} onRetry={error ? reload : undefined} />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Formation</th><th>Condition</th><th>Année</th><th>Validité</th><th>Statut</th><th /></tr></thead>
          <tbody>
            {data?.items.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.program_name}</strong><div className="code">{r.school} · {r.program_code}</div></td>
                <td>
                  <div>{r.description}{!r.is_mandatory && <span className="muted small"> (souhaitée)</span>}</div>
                  <div className="muted small">
                    {REQUIREMENT_CATEGORIES[r.category]} · {REQUIREMENT_KINDS[r.kind]}
                    {r.min_average != null && ` · ${r.min_average}/20`}
                    {r.required_program_name && ` · exige : ${r.required_program_name}`}
                    {r.accepted_bac_series?.length ? ` · ${r.accepted_bac_series.join(", ")}` : ""}
                  </div>
                </td>
                <td className="nowrap">{r.academic_year ?? <span className="muted">Toutes</span>}</td>
                <td className="small">{validity(r.valid_from, r.valid_until)}</td>
                <td><StatusBadge visibility={r.visibility} /></td>
                <td className="actions">{canWrite && <>
                  <button className="btn btn-ghost btn-sm" disabled={r.status === "archived"} onClick={() => setEditing(r)}>Modifier</button>
                  <PublicationActions status={r.status} onChange={(s) => setStatus(r, s)} disabled={action.busy} />
                  <button className="btn btn-ghost btn-sm danger" onClick={() => remove(r)}>Supprimer</button>
                </>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Chargement…</div>}
        {data && data.items.length === 0 && <div className="empty">Aucune condition d&apos;admission.</div>}
      </div>
      {data && <Pagination page={page} size={SIZE} total={data.total} onChange={setPage} />}
      {editing && <AdmissionForm req={editing === "new" ? null : editing} defaultProgram={programId}
                                 onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
    </>
  );
}

function AdmissionForm({ req, defaultProgram, onClose, onSaved }: {
  req: AdmissionRequirement | null; defaultProgram: string; onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState({
    program_id: req?.program_id ?? defaultProgram, category: (req?.category ?? "admission") as RequirementCategory,
    kind: (req?.kind ?? "document") as RequirementKind, description: req?.description ?? "",
    min_average: str(req?.min_average), accepted_bac_series: (req?.accepted_bac_series ?? []).join(", "),
    required_program_id: req?.required_program_id ?? "", academic_year: req?.academic_year ?? "",
    is_mandatory: req?.is_mandatory ?? true, position: str(req?.position ?? 0),
    valid_from: req?.valid_from ?? "", valid_until: req?.valid_until ?? "",
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const { busy, error, run } = useSubmit();

  async function submit() {
    const series = f.accepted_bac_series.split(",").map((s) => s.trim()).filter(Boolean);
    const body = {
      category: f.category, kind: f.kind, description: f.description, min_average: toNumber(f.min_average),
      accepted_bac_series: series.length ? series : null, required_program_id: f.required_program_id || null,
      academic_year: f.academic_year || null, is_mandatory: f.is_mandatory, position: Number(f.position) || 0,
      valid_from: blankToNull(f.valid_from), valid_until: blankToNull(f.valid_until),
    };
    if (await run(() => req ? catalogApi.admissionRequirements.update(req.id, body)
                            : catalogApi.admissionRequirements.create({ program_id: f.program_id, ...body }))) onSaved();
  }

  return (
    <FormModal title={req ? "Modifier la condition d'admission" : "Nouvelle condition d'admission"} onClose={onClose}
               onSubmit={submit} busy={busy} error={error} wide>
      {req?.status === "published" && <p className="full small banner" style={{ margin: 0 }}>Cette condition est publiée : la modification sera immédiatement visible par les candidats.</p>}
      <Field label="Formation *" full><ProgramSelect value={f.program_id} onChange={(v) => set("program_id", v)} required disabled={!!req} /></Field>
      <Field label="Catégorie *">
        <select value={f.category} onChange={(e) => set("category", e.target.value as RequirementCategory)}>
          {Object.entries(REQUIREMENT_CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </Field>
      <Field label="Type *">
        <select value={f.kind} onChange={(e) => set("kind", e.target.value as RequirementKind)}>
          {Object.entries(REQUIREMENT_KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </Field>
      <Field label="Description (texte affiché aux candidats) *" full>
        <textarea value={f.description} onChange={(e) => set("description", e.target.value)} required minLength={3} />
      </Field>
      {f.kind === "minimum_average" && (
        <Field label="Moyenne minimale (/20) *"><input type="number" min={0} max={20} step="0.01" value={f.min_average} onChange={(e) => set("min_average", e.target.value)} required /></Field>
      )}
      {f.kind === "bac_series" && (
        <Field label="Séries du bac acceptées" hint="Séparées par des virgules" full>
          <input value={f.accepted_bac_series} onChange={(e) => set("accepted_bac_series", e.target.value)} placeholder="Mathématiques, Sciences techniques" />
        </Field>
      )}
      {f.kind === "prior_diploma" && (
        <Field label="Formation exigée" hint="Ex. le cycle préparatoire pour le cycle ingénieur">
          <ProgramSelect value={f.required_program_id} onChange={(v) => set("required_program_id", v)} allLabel="Aucune (diplôme externe)" />
        </Field>
      )}
      <Field label="Année universitaire"><YearSelect value={f.academic_year} onChange={(v) => set("academic_year", v)} allLabel="Toutes les années" /></Field>
      <Field label="Ordre d'affichage"><input type="number" min={0} max={1000} value={f.position} onChange={(e) => set("position", e.target.value)} /></Field>
      <label className="check"><input type="checkbox" checked={f.is_mandatory} onChange={(e) => set("is_mandatory", e.target.checked)} />Obligatoire</label>
      <ValidityFields from={f.valid_from} until={f.valid_until} academicYear={f.academic_year || undefined}
                      onChange={(a, b) => setF((s) => ({ ...s, valid_from: a, valid_until: b }))} />
      {!req && <p className="full muted small" style={{ margin: 0 }}>Créée en brouillon : utilisez « Publier » pour la rendre officielle.</p>}
    </FormModal>
  );
}
