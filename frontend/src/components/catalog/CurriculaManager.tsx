"use client";
// Programmes pédagogiques (par formation / spécialité / année, versionnés) et leurs matières.
import { useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/ui/Modal";
import Pagination from "@/components/ui/Pagination";
import { ActiveBadge } from "@/components/ui/StatusBadge";
import { catalogApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import { blankToNull, currentAcademicYear, str, toNumber } from "@/lib/catalog";
import type { Curriculum, CurriculumDetail, CurriculumSubject, CurriculumSubjectInput } from "@/types/api";
import { confirmDelete, Field, FormModal, ProgramSelect, useCatalog, useSubmit, YearSelect } from "./shared";

const SIZE = 20;

export default function CurriculaManager() {
  const { canWrite } = useCatalog();
  const [programId, setProgramId] = useState("");
  const [year, setYear] = useState("");
  const [active, setActive] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Curriculum | "new" | null>(null);
  const [opened, setOpened] = useState<string | null>(null);
  const action = useSubmit();
  const { data, error, loading, reload } = useApi(
    () => catalogApi.curricula.list({ program_id: programId, academic_year: year, is_active: active || undefined, page, size: SIZE }),
    [programId, year, active, page]);

  async function remove(c: Curriculum) {
    if (confirmDelete(`le programme ${c.program_name} ${c.academic_year} v${c.version}`) &&
        await action.run(() => catalogApi.curricula.remove(c.id))) reload();
  }

  return (
    <>
      <div className="filters">
        <ProgramSelect value={programId} onChange={(v) => { setProgramId(v); setPage(1); }} allLabel="Toutes les formations" />
        <YearSelect value={year} onChange={(v) => { setYear(v); setPage(1); }} allLabel="Toutes les années" />
        <select value={active} onChange={(e) => { setActive(e.target.value); setPage(1); }} aria-label="État">
          <option value="">Actifs et inactifs</option><option value="true">Actifs</option><option value="false">Inactifs</option>
        </select>
        {canWrite && <button className="btn" onClick={() => setEditing("new")}>+ Nouveau programme</button>}
      </div>
      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} onRetry={error ? reload : undefined} />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Formation</th><th>Parcours</th><th>Année</th><th>Version</th><th>Matières</th><th>Crédits</th><th>État</th><th /></tr></thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id}>
                <td><strong>{c.program_name}</strong><div className="code">{c.school} · {c.program_code}</div></td>
                <td>{c.specialty_name ?? <span className="muted">Tronc commun</span>}</td>
                <td className="nowrap">{c.academic_year}</td>
                <td>v{c.version}</td>
                <td>{c.subjects_count}</td>
                <td>{c.total_credits}</td>
                <td><ActiveBadge active={c.is_active} /></td>
                <td className="actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => setOpened(c.id)}>Matières</button>
                  {canWrite && <>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditing(c)}>Modifier</button>
                    <button className="btn btn-ghost btn-sm danger" onClick={() => remove(c)}>Supprimer</button>
                  </>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Chargement…</div>}
        {data && data.items.length === 0 && <div className="empty">Aucun programme pédagogique.</div>}
      </div>
      {data && <Pagination page={page} size={SIZE} total={data.total} onChange={setPage} />}
      {editing && <CurriculumForm curriculum={editing === "new" ? null : editing} defaultProgram={programId}
                                  onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
      {opened && <CurriculumSubjectsModal id={opened} onClose={() => { setOpened(null); reload(); }} />}
    </>
  );
}

function SpecialtySelect({ programId, value, onChange }: { programId: string; value: string; onChange: (v: string) => void }) {
  const { data } = useApi(() => programId ? catalogApi.programs.specialties(programId) : Promise.resolve(null), [programId]);
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} disabled={!programId}>
      <option value="">Tronc commun (toute la formation)</option>
      {data?.items.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
    </select>
  );
}

function CurriculumForm({ curriculum, defaultProgram, onClose, onSaved }: {
  curriculum: Curriculum | null; defaultProgram: string; onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState({
    program_id: curriculum?.program_id ?? defaultProgram, specialty_id: curriculum?.specialty_id ?? "",
    academic_year: curriculum?.academic_year ?? currentAcademicYear(), version: str(curriculum?.version ?? 1),
    description: str(curriculum?.description), is_active: curriculum?.is_active ?? true,
  });
  const { busy, error, run } = useSubmit();
  async function submit() {
    const body = { specialty_id: f.specialty_id || null, academic_year: f.academic_year, version: Number(f.version) || 1,
                   description: blankToNull(f.description), is_active: f.is_active };
    if (await run(() => curriculum ? catalogApi.curricula.update(curriculum.id, body)
                                   : catalogApi.curricula.create({ program_id: f.program_id, ...body }))) onSaved();
  }
  return (
    <FormModal title={curriculum ? "Modifier le programme pédagogique" : "Nouveau programme pédagogique"} onClose={onClose}
               onSubmit={submit} busy={busy} error={error}>
      <Field label="Formation *" full>
        <ProgramSelect value={f.program_id} onChange={(v) => setF({ ...f, program_id: v, specialty_id: "" })} required disabled={!!curriculum} />
      </Field>
      <Field label="Parcours / spécialité" full><SpecialtySelect programId={f.program_id} value={f.specialty_id} onChange={(v) => setF({ ...f, specialty_id: v })} /></Field>
      <Field label="Année universitaire *"><YearSelect value={f.academic_year} onChange={(v) => setF({ ...f, academic_year: v })} required /></Field>
      <Field label="Version *"><input type="number" min={1} value={f.version} onChange={(e) => setF({ ...f, version: e.target.value })} required /></Field>
      <Field label="Description" full><textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <label className="check full"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />
        Version active (les autres versions de la même année seront désactivées)</label>
    </FormModal>
  );
}

function CurriculumSubjectsModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { canWrite } = useCatalog();
  const { data: c, error, reload } = useApi(() => catalogApi.curricula.detail(id), [id]);
  const subjects = useApi(() => catalogApi.subjects.list({ size: 100, sort: "name" }), []);
  const [current, setCurrent] = useState<CurriculumDetail | null>(null);
  const cur = current ?? c;
  const empty = { subject_id: "", study_year: "1", semester: "1", coefficient: "", credits: "", is_mandatory: true };
  const [row, setRow] = useState(empty);
  const [dup, setDup] = useState({ academic_year: "", is_active: false });
  const action = useSubmit();

  const apply = (p: Promise<CurriculumDetail>) => action.run(async () => setCurrent(await p));

  async function add() {
    if (!cur) return;
    const ok = await apply(catalogApi.curricula.addSubject(cur.id, {
      subject_id: row.subject_id, study_year: Number(row.study_year), semester: Number(row.semester),
      coefficient: toNumber(row.coefficient), credits: toNumber(row.credits), is_mandatory: row.is_mandatory }));
    if (ok) setRow(empty);
  }
  const patch = (s: CurriculumSubject, body: Partial<CurriculumSubjectInput>) =>
    cur && apply(catalogApi.curricula.updateSubject(cur.id, s.id, body));
  const remove = (s: CurriculumSubject) => cur && apply(catalogApi.curricula.removeSubject(cur.id, s.id));
  async function duplicate() {
    if (!cur) return;
    const ok = await action.run(() => catalogApi.curricula.duplicate(cur.id, { academic_year: dup.academic_year, is_active: dup.is_active }));
    if (ok) { onClose(); }
  }

  return (
    <Modal title={cur ? `${cur.program_name} · ${cur.specialty_name ?? "Tronc commun"} · ${cur.academic_year} v${cur.version}` : "Programme"} onClose={onClose} wide>
      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} onRetry={error ? reload : undefined} />}
      {cur && <>
        <p className="muted small" style={{ marginTop: 0 }}>{cur.subjects.length} matière(s) · {cur.subjects.reduce((n, s) => n + (s.credits ?? 0), 0)} crédits</p>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Matière</th><th>Année</th><th>Semestre</th><th>Coef.</th><th>Crédits</th><th>Obligatoire</th><th /></tr></thead>
            <tbody>
              {cur.subjects.map((s) => (
                <tr key={s.id}>
                  <td><strong>{s.subject_name}</strong><div className="code">{s.subject_code}</div></td>
                  <td><NumberCell value={s.study_year} min={1} max={8} disabled={!canWrite} onSave={(v) => patch(s, { study_year: v ?? 1 })} /></td>
                  <td><NumberCell value={s.semester} min={1} max={16} disabled={!canWrite} onSave={(v) => patch(s, { semester: v ?? 1 })} /></td>
                  <td><NumberCell value={s.coefficient} min={0} step="0.5" disabled={!canWrite} onSave={(v) => patch(s, { coefficient: v })} /></td>
                  <td><NumberCell value={s.credits} min={0} max={60} disabled={!canWrite} onSave={(v) => patch(s, { credits: v })} /></td>
                  <td><input type="checkbox" checked={s.is_mandatory} disabled={!canWrite} onChange={(e) => patch(s, { is_mandatory: e.target.checked })} /></td>
                  <td className="actions">{canWrite && <button className="btn btn-ghost btn-sm danger" onClick={() => remove(s)}>Retirer</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {cur.subjects.length === 0 && <div className="empty">Aucune matière dans ce programme.</div>}
        </div>

        {canWrite && <>
          <h4 className="section">Ajouter une matière</h4>
          <form className="row" onSubmit={(e) => { e.preventDefault(); add(); }}>
            <select value={row.subject_id} onChange={(e) => setRow({ ...row, subject_id: e.target.value })} required aria-label="Matière">
              <option value="" disabled>Matière…</option>
              {subjects.data?.items.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.code})</option>)}
            </select>
            <input type="number" min={1} max={8} style={{ width: 80 }} value={row.study_year} onChange={(e) => setRow({ ...row, study_year: e.target.value })} title="Année" aria-label="Année" />
            <input type="number" min={1} max={16} style={{ width: 80 }} value={row.semester} onChange={(e) => setRow({ ...row, semester: e.target.value })} title="Semestre" aria-label="Semestre" />
            <input type="number" min={0} step="0.5" style={{ width: 90 }} placeholder="Coef." value={row.coefficient} onChange={(e) => setRow({ ...row, coefficient: e.target.value })} aria-label="Coefficient" />
            <input type="number" min={0} max={60} style={{ width: 90 }} placeholder="Crédits" value={row.credits} onChange={(e) => setRow({ ...row, credits: e.target.value })} aria-label="Crédits" />
            <label className="check"><input type="checkbox" checked={row.is_mandatory} onChange={(e) => setRow({ ...row, is_mandatory: e.target.checked })} />Obligatoire</label>
            <button className="btn" disabled={action.busy}>Ajouter</button>
          </form>
          <p className="muted small">Matière absente de la liste ? Créez-la dans l&apos;onglet « Matières ».</p>

          <h4 className="section">Copier ce programme</h4>
          <form className="row" onSubmit={(e) => { e.preventDefault(); duplicate(); }}>
            <YearSelect value={dup.academic_year} onChange={(v) => setDup({ ...dup, academic_year: v })} allLabel="Vers l'année…" required />
            <label className="check"><input type="checkbox" checked={dup.is_active} onChange={(e) => setDup({ ...dup, is_active: e.target.checked })} />Activer la copie</label>
            <button className="btn btn-light" disabled={action.busy || !dup.academic_year}>Dupliquer (nouvelle version)</button>
          </form>
        </>}
      </>}
    </Modal>
  );
}

/** Cellule numérique éditable : enregistre quand on quitte le champ. */
function NumberCell({ value, onSave, min, max, step, disabled }: {
  value: number | null; onSave: (v: number | null) => void; min?: number; max?: number; step?: string; disabled?: boolean;
}) {
  const [v, setV] = useState(str(value));
  return (
    <input type="number" style={{ width: 72 }} value={v} min={min} max={max} step={step} disabled={disabled}
           onChange={(e) => setV(e.target.value)} onBlur={() => { if (v !== str(value)) onSave(toNumber(v)); }} />
  );
}
