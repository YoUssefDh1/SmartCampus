"use client";
// Matières : référentiel commun, réutilisé par les programmes pédagogiques.
import { useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Pagination from "@/components/ui/Pagination";
import { catalogApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import { blankToNull, str } from "@/lib/catalog";
import { useDebounced } from "@/lib/useDebounced";
import type { Subject } from "@/types/api";
import { confirmDelete, Field, FormModal, ProgramSelect, useCatalog, useSubmit } from "./shared";

const SIZE = 25;

export default function SubjectsManager() {
  const { canWrite } = useCatalog();
  const [text, setText] = useState("");
  const q = useDebounced(text);
  const [programId, setProgramId] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Subject | "new" | null>(null);
  const action = useSubmit();
  const { data, error, loading, reload } = useApi(
    () => catalogApi.subjects.list({ q, program_id: programId, page, size: SIZE }), [q, programId, page]);

  async function remove(s: Subject) {
    if (confirmDelete(`la matière « ${s.name} »`) && await action.run(() => catalogApi.subjects.remove(s.id))) reload();
  }

  return (
    <>
      <div className="filters">
        <input className="search" type="search" placeholder="Rechercher une matière (code, nom)…" value={text}
               onChange={(e) => { setText(e.target.value); setPage(1); }} />
        <ProgramSelect value={programId} onChange={(v) => { setProgramId(v); setPage(1); }} allLabel="Utilisées par toute formation" />
        {canWrite && <button className="btn" onClick={() => setEditing("new")}>+ Nouvelle matière</button>}
      </div>
      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} onRetry={error ? reload : undefined} />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Code</th><th>Matière</th><th>Utilisée dans</th><th /></tr></thead>
          <tbody>
            {data?.items.map((s) => (
              <tr key={s.id}>
                <td className="code">{s.code}</td>
                <td><strong>{s.name}</strong>{s.description && <div className="muted small">{s.description}</div>}</td>
                <td>{s.usage_count} programme{s.usage_count > 1 ? "s" : ""}</td>
                <td className="actions">{canWrite && <>
                  <button className="btn btn-ghost btn-sm" onClick={() => setEditing(s)}>Modifier</button>
                  <button className="btn btn-ghost btn-sm danger" onClick={() => remove(s)} disabled={s.usage_count > 0}
                          title={s.usage_count > 0 ? "Retirez-la d'abord des programmes" : undefined}>Supprimer</button>
                </>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Chargement…</div>}
        {data && data.items.length === 0 && <div className="empty">Aucune matière.</div>}
      </div>
      {data && <Pagination page={page} size={SIZE} total={data.total} onChange={setPage} />}
      {editing && <SubjectForm subject={editing === "new" ? null : editing} onClose={() => setEditing(null)}
                               onSaved={() => { setEditing(null); reload(); }} />}
    </>
  );
}

function SubjectForm({ subject, onClose, onSaved }: { subject: Subject | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ code: subject?.code ?? "", name: subject?.name ?? "", description: str(subject?.description) });
  const { busy, error, run } = useSubmit();
  async function submit() {
    const body = { code: f.code, name: f.name, description: blankToNull(f.description) };
    if (await run(() => subject ? catalogApi.subjects.update(subject.id, body) : catalogApi.subjects.create(body))) onSaved();
  }
  return (
    <FormModal title={subject ? `Modifier ${subject.name}` : "Nouvelle matière"} onClose={onClose} onSubmit={submit} busy={busy} error={error}>
      <Field label="Code *"><input value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} required maxLength={30} /></Field>
      <Field label="Nom *"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required minLength={2} maxLength={150} /></Field>
      <Field label="Description" full><textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
    </FormModal>
  );
}
