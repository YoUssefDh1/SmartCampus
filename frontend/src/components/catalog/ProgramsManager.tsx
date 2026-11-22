"use client";
// Formations : ajouter, consulter, modifier, supprimer, rechercher, filtrer + spécialités.
import { useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Modal from "@/components/ui/Modal";
import Pagination from "@/components/ui/Pagination";
import { ActiveBadge } from "@/components/ui/StatusBadge";
import { catalogApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import { blankToNull, CYCLES, LANGUAGES, str, toNumber } from "@/lib/catalog";
import { useDebounced } from "@/lib/useDebounced";
import type { Cycle, Program, Specialty } from "@/types/api";
import { confirmDelete, Field, FormModal, useCatalog, useSubmit } from "./shared";

const SIZE = 20;

export default function ProgramsManager() {
  const ctx = useCatalog();
  const [text, setText] = useState("");
  const q = useDebounced(text);
  const [school, setSchool] = useState("");
  const [cycle, setCycle] = useState("");
  const [active, setActive] = useState("");
  const [sort, setSort] = useState("name");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Program | "new" | null>(null);
  const [specialtiesOf, setSpecialtiesOf] = useState<Program | null>(null);
  const action = useSubmit();

  const { data, error, loading, reload } = useApi(
    () => catalogApi.programs.list({ q, school, cycle, is_active: active || undefined, sort, page, size: SIZE }),
    [q, school, cycle, active, sort, page]);

  const refresh = () => { reload(); ctx.reloadPrograms(); };
  const reset = (fn: (v: string) => void) => (v: string) => { fn(v); setPage(1); };

  async function remove(p: Program) {
    if (confirmDelete(`la formation « ${p.name} » (spécialités, programmes, tarifs et conditions compris)`)) {
      if (await action.run(() => catalogApi.programs.remove(p.id))) refresh();
    }
  }

  return (
    <>
      <div className="filters">
        <input className="search" type="search" placeholder="Rechercher (nom, code, diplôme, débouchés)…" value={text}
               onChange={(e) => { setText(e.target.value); setPage(1); }} />
        {ctx.isAdmin && (
          <select value={school} onChange={(e) => reset(setSchool)(e.target.value)} aria-label="École">
            <option value="">Toutes les écoles</option>
            {ctx.institutions.map((i) => <option key={i.id} value={i.code}>{i.code}</option>)}
          </select>
        )}
        <select value={cycle} onChange={(e) => reset(setCycle)(e.target.value)} aria-label="Niveau">
          <option value="">Tous les niveaux</option>
          {Object.entries(CYCLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={active} onChange={(e) => reset(setActive)(e.target.value)} aria-label="État">
          <option value="">Actives et inactives</option><option value="true">Actives</option><option value="false">Inactives</option>
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Tri">
          <option value="name">Nom A→Z</option><option value="code">Code</option><option value="school">École</option>
          <option value="-updated_at">Dernières modifiées</option>
        </select>
        {ctx.canWrite && <button className="btn" onClick={() => setEditing("new")}>+ Nouvelle formation</button>}
      </div>

      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} onRetry={error ? reload : undefined} />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Formation</th><th>École</th><th>Niveau</th><th>Durée</th><th>Langues</th><th>Spécialités</th><th>État</th><th /></tr></thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id}>
                <td><strong>{p.name}</strong><div className="code">{p.code}</div></td>
                <td>{p.school}</td>
                <td>{p.level}</td>
                <td>{p.duration_years ? `${p.duration_years} an${p.duration_years > 1 ? "s" : ""}` : "—"}</td>
                <td>{p.teaching_languages.map((l) => l.toUpperCase()).join(", ") || "—"}</td>
                <td><button className="btn btn-ghost btn-sm" onClick={() => setSpecialtiesOf(p)}>{p.specialties_count} · gérer</button></td>
                <td><ActiveBadge active={p.is_active} /></td>
                <td className="actions">
                  {ctx.canWrite && <>
                    <button className="btn btn-ghost btn-sm" onClick={() => setEditing(p)}>Modifier</button>
                    <button className="btn btn-ghost btn-sm danger" onClick={() => remove(p)}>Supprimer</button>
                  </>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Chargement…</div>}
        {data && data.items.length === 0 && <div className="empty">Aucune formation.</div>}
      </div>
      {data && <Pagination page={page} size={SIZE} total={data.total} onChange={setPage} />}

      {editing && <ProgramForm program={editing === "new" ? null : editing} onClose={() => setEditing(null)}
                               onSaved={() => { setEditing(null); refresh(); }} />}
      {specialtiesOf && <SpecialtiesModal program={specialtiesOf} onClose={() => { setSpecialtiesOf(null); refresh(); }} />}
    </>
  );
}

function ProgramForm({ program, onClose, onSaved }: { program: Program | null; onClose: () => void; onSaved: () => void }) {
  const ctx = useCatalog();
  const [f, setF] = useState({
    institution_id: program?.institution_id ?? "", code: program?.code ?? "", name: program?.name ?? "",
    cycle: (program?.cycle ?? "bachelor") as Cycle, duration_years: str(program?.duration_years),
    degree: str(program?.degree), capacity: str(program?.capacity),
    teaching_languages: program?.teaching_languages ?? ["fr"], description: str(program?.description),
    career_outcomes: str(program?.career_outcomes), is_active: program?.is_active ?? true,
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const { busy, error, run } = useSubmit();

  function toggleLanguage(l: string) {
    set("teaching_languages", f.teaching_languages.includes(l) ? f.teaching_languages.filter((x) => x !== l) : [...f.teaching_languages, l]);
  }

  async function submit() {
    const body = {
      code: f.code, name: f.name, cycle: f.cycle, duration_years: toNumber(f.duration_years), degree: blankToNull(f.degree),
      capacity: toNumber(f.capacity), teaching_languages: f.teaching_languages, description: blankToNull(f.description),
      career_outcomes: blankToNull(f.career_outcomes), is_active: f.is_active,
      ...(ctx.isAdmin && f.institution_id ? { institution_id: f.institution_id } : {}),
    };
    if (await run(() => program ? catalogApi.programs.update(program.id, body) : catalogApi.programs.create(body))) onSaved();
  }

  return (
    <FormModal title={program ? `Modifier ${program.name}` : "Nouvelle formation"} onClose={onClose} onSubmit={submit}
               busy={busy} error={error} wide>
      {ctx.isAdmin && (
        <Field label="École *">
          <select value={f.institution_id} onChange={(e) => set("institution_id", e.target.value)} required>
            <option value="" disabled>Choisir…</option>
            {ctx.institutions.map((i) => <option key={i.id} value={i.id}>{i.code} · {i.name}</option>)}
          </select>
        </Field>
      )}
      <Field label="Code *" hint="Lettres, chiffres et tirets (ex. ING-INFO)">
        <input value={f.code} onChange={(e) => set("code", e.target.value.toUpperCase())} required maxLength={30} />
      </Field>
      <Field label="Nom *" full><input value={f.name} onChange={(e) => set("name", e.target.value)} required minLength={2} maxLength={200} /></Field>
      <Field label="Niveau (cycle) *">
        <select value={f.cycle} onChange={(e) => set("cycle", e.target.value as Cycle)}>
          {Object.entries(CYCLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </Field>
      <Field label="Durée (années)"><input type="number" min={1} max={10} value={f.duration_years} onChange={(e) => set("duration_years", e.target.value)} /></Field>
      <Field label="Diplôme délivré"><input value={f.degree} onChange={(e) => set("degree", e.target.value)} maxLength={150} /></Field>
      <Field label="Capacité (places)"><input type="number" min={0} value={f.capacity} onChange={(e) => set("capacity", e.target.value)} /></Field>
      <Field label="Langues d'enseignement">
        <div className="row">
          {Object.entries(LANGUAGES).map(([k, v]) => (
            <label key={k} className="check"><input type="checkbox" checked={f.teaching_languages.includes(k)} onChange={() => toggleLanguage(k)} />{v}</label>
          ))}
        </div>
      </Field>
      <Field label="Description" full><textarea value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Débouchés" full><textarea value={f.career_outcomes} onChange={(e) => set("career_outcomes", e.target.value)} /></Field>
      <label className="check full"><input type="checkbox" checked={f.is_active} onChange={(e) => set("is_active", e.target.checked)} />
        Formation active (visible dans le catalogue public)</label>
    </FormModal>
  );
}

function SpecialtiesModal({ program, onClose }: { program: Program; onClose: () => void }) {
  const { canWrite } = useCatalog();
  const { data, error, reload } = useApi(() => catalogApi.programs.specialties(program.id), [program.id]);
  const [draft, setDraft] = useState({ name: "", description: "" });
  const [editId, setEditId] = useState<string | null>(null);
  const [edit, setEdit] = useState({ name: "", description: "" });
  const action = useSubmit();

  async function add() {
    if (await action.run(() => catalogApi.programs.addSpecialty(program.id, { name: draft.name, description: blankToNull(draft.description), is_active: true }))) {
      setDraft({ name: "", description: "" }); reload();
    }
  }
  async function save(s: Specialty) {
    if (await action.run(() => catalogApi.specialties.update(s.id, { name: edit.name, description: blankToNull(edit.description) }))) {
      setEditId(null); reload();
    }
  }
  async function toggle(s: Specialty) {
    if (await action.run(() => catalogApi.specialties.update(s.id, { is_active: !s.is_active }))) reload();
  }
  async function remove(s: Specialty) {
    if (confirmDelete(`la spécialité « ${s.name} »`) && await action.run(() => catalogApi.specialties.remove(s.id))) reload();
  }

  return (
    <Modal title={`Spécialités · ${program.name}`} onClose={onClose} wide>
      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Spécialité</th><th>Programmes</th><th>État</th><th /></tr></thead>
          <tbody>
            {data?.items.map((s) => editId === s.id ? (
              <tr key={s.id}>
                <td colSpan={3}>
                  <div className="row">
                    <input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} aria-label="Nom" />
                    <input className="search" value={edit.description} placeholder="Description" onChange={(e) => setEdit({ ...edit, description: e.target.value })} />
                  </div>
                </td>
                <td className="actions">
                  <button className="btn btn-sm" onClick={() => save(s)}>OK</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditId(null)}>Annuler</button>
                </td>
              </tr>
            ) : (
              <tr key={s.id}>
                <td><strong>{s.name}</strong>{s.description && <div className="muted small">{s.description}</div>}</td>
                <td>{s.curricula_count}</td>
                <td><ActiveBadge active={s.is_active} /></td>
                <td className="actions">
                  {canWrite && <>
                    <button className="btn btn-ghost btn-sm" onClick={() => { setEditId(s.id); setEdit({ name: s.name, description: str(s.description) }); }}>Modifier</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => toggle(s)}>{s.is_active ? "Désactiver" : "Activer"}</button>
                    <button className="btn btn-ghost btn-sm danger" onClick={() => remove(s)}>Supprimer</button>
                  </>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && <div className="empty">Aucune spécialité.</div>}
      </div>
      {canWrite && (
        <form className="row" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); add(); }}>
          <input placeholder="Nouvelle spécialité" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} required minLength={2} />
          <input className="search" placeholder="Description (optionnelle)" value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
          <button className="btn" disabled={action.busy}>Ajouter</button>
        </form>
      )}
    </Modal>
  );
}
