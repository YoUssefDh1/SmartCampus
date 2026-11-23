"use client";
// Frais de scolarité : CRUD + publication + période de validité.
import { useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Pagination from "@/components/ui/Pagination";
import StatusBadge from "@/components/ui/StatusBadge";
import { catalogApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import { blankToNull, currentAcademicYear, FEE_TYPES, money, str, toNumber, validity } from "@/lib/catalog";
import type { FeeType, PublicationStatus, TuitionFee } from "@/types/api";
import {
  confirmDelete, Field, FormModal, ProgramSelect, PublicationActions, useCatalog, useSubmit, ValidityFields,
  VisibilitySelect, YearSelect,
} from "./shared";

const SIZE = 25;

export default function TuitionManager() {
  const { canWrite } = useCatalog();
  const [programId, setProgramId] = useState("");
  const [year, setYear] = useState("");
  const [feeType, setFeeType] = useState("");
  const [visibility, setVisibility] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<TuitionFee | "new" | null>(null);
  const action = useSubmit();
  const { data, error, loading, reload } = useApi(
    () => catalogApi.tuitionFees.list({ program_id: programId, academic_year: year, fee_type: feeType, visibility, page, size: SIZE }),
    [programId, year, feeType, visibility, page]);
  const f = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1); };

  async function setStatus(fee: TuitionFee, s: PublicationStatus) {
    if (await action.run(() => catalogApi.tuitionFees.setStatus(fee.id, s))) reload();
  }
  async function remove(fee: TuitionFee) {
    if (confirmDelete("ce tarif") && await action.run(() => catalogApi.tuitionFees.remove(fee.id))) reload();
  }

  return (
    <>
      <div className="filters">
        <ProgramSelect value={programId} onChange={f(setProgramId)} allLabel="Toutes les formations" />
        <YearSelect value={year} onChange={f(setYear)} allLabel="Toutes les années" />
        <select value={feeType} onChange={(e) => f(setFeeType)(e.target.value)} aria-label="Type de frais">
          <option value="">Tous les frais</option>
          {Object.entries(FEE_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <VisibilitySelect value={visibility} onChange={f(setVisibility)} />
        {canWrite && <button className="btn" onClick={() => setEditing("new")}>+ Nouveau tarif</button>}
      </div>
      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} onRetry={error ? reload : undefined} />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Formation</th><th>Année</th><th>Frais</th><th>Niveau</th><th style={{ textAlign: "right" }}>Montant</th><th>Validité</th><th>Statut</th><th /></tr></thead>
          <tbody>
            {data?.items.map((fee) => (
              <tr key={fee.id}>
                <td><strong>{fee.program_name}</strong><div className="code">{fee.school} · {fee.program_code}</div></td>
                <td className="nowrap">{fee.academic_year}</td>
                <td>{FEE_TYPES[fee.fee_type]}{fee.description && <div className="muted small">{fee.description}</div>}</td>
                <td>{fee.study_year ? `${fee.study_year}e année` : "Toutes"}</td>
                <td style={{ textAlign: "right" }} className="price">{money(fee.amount, fee.currency)}</td>
                <td className="small">{validity(fee.valid_from, fee.valid_until)}</td>
                <td><StatusBadge visibility={fee.visibility} /></td>
                <td className="actions">{canWrite && <>
                  <button className="btn btn-ghost btn-sm" disabled={fee.status === "archived"} onClick={() => setEditing(fee)}>Modifier</button>
                  <PublicationActions status={fee.status} onChange={(s) => setStatus(fee, s)} disabled={action.busy} />
                  <button className="btn btn-ghost btn-sm danger" onClick={() => remove(fee)}>Supprimer</button>
                </>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Chargement…</div>}
        {data && data.items.length === 0 && <div className="empty">Aucun tarif.</div>}
      </div>
      {data && <Pagination page={page} size={SIZE} total={data.total} onChange={setPage} />}
      {editing && <TuitionForm fee={editing === "new" ? null : editing} defaultProgram={programId}
                               onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
    </>
  );
}

function TuitionForm({ fee, defaultProgram, onClose, onSaved }: {
  fee: TuitionFee | null; defaultProgram: string; onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState({
    program_id: fee?.program_id ?? defaultProgram, academic_year: fee?.academic_year ?? currentAcademicYear(),
    fee_type: (fee?.fee_type ?? "tuition") as FeeType, study_year: str(fee?.study_year), amount: str(fee?.amount),
    currency: fee?.currency ?? "TND", description: str(fee?.description),
    valid_from: fee?.valid_from ?? "", valid_until: fee?.valid_until ?? "",
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const { busy, error, run } = useSubmit();

  async function submit() {
    const body = {
      academic_year: f.academic_year, fee_type: f.fee_type, study_year: toNumber(f.study_year),
      amount: toNumber(f.amount) ?? 0, currency: f.currency.toUpperCase(), description: blankToNull(f.description),
      valid_from: blankToNull(f.valid_from), valid_until: blankToNull(f.valid_until),
    };
    if (await run(() => fee ? catalogApi.tuitionFees.update(fee.id, body)
                            : catalogApi.tuitionFees.create({ program_id: f.program_id, ...body }))) onSaved();
  }

  return (
    <FormModal title={fee ? "Modifier le tarif" : "Nouveau tarif"} onClose={onClose} onSubmit={submit} busy={busy} error={error}>
      {fee?.status === "published" && <p className="full small banner" style={{ margin: 0 }}>Ce tarif est publié : la modification sera immédiatement visible par les candidats.</p>}
      <Field label="Formation *" full><ProgramSelect value={f.program_id} onChange={(v) => set("program_id", v)} required disabled={!!fee} /></Field>
      <Field label="Année universitaire *"><YearSelect value={f.academic_year} onChange={(v) => set("academic_year", v)} required /></Field>
      <Field label="Type de frais *">
        <select value={f.fee_type} onChange={(e) => set("fee_type", e.target.value as FeeType)}>
          {Object.entries(FEE_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </Field>
      <Field label="Montant *"><input type="number" min={0} step="0.001" value={f.amount} onChange={(e) => set("amount", e.target.value)} required /></Field>
      <Field label="Devise"><input value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} maxLength={3} pattern="[A-Za-z]{3}" /></Field>
      <Field label="Année d'étude" hint="Vide = toutes les années de la formation">
        <input type="number" min={1} max={8} value={f.study_year} onChange={(e) => set("study_year", e.target.value)} />
      </Field>
      <Field label="Description"><input value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
      <ValidityFields from={f.valid_from} until={f.valid_until} academicYear={f.academic_year}
                      onChange={(a, b) => setF((s) => ({ ...s, valid_from: a, valid_until: b }))} />
      {!fee && <p className="full muted small" style={{ margin: 0 }}>Créé en brouillon : utilisez « Publier » pour le rendre officiel.</p>}
    </FormModal>
  );
}
