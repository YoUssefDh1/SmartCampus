"use client";
// Modalités de paiement (plans + échéances) : CRUD + publication + période de validité.
import { useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Pagination from "@/components/ui/Pagination";
import StatusBadge from "@/components/ui/StatusBadge";
import { catalogApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import { blankToNull, currentAcademicYear, day, money, PAYMENT_METHODS, str, toNumber, validity } from "@/lib/catalog";
import type { Installment, PaymentMethod, PaymentPlan, PublicationStatus } from "@/types/api";
import {
  confirmDelete, Field, FormModal, ProgramSelect, PublicationActions, useCatalog, useSubmit, ValidityFields,
  VisibilitySelect, YearSelect,
} from "./shared";

const SIZE = 25;

export default function PaymentPlansManager() {
  const { canWrite } = useCatalog();
  const [programId, setProgramId] = useState("");
  const [year, setYear] = useState("");
  const [method, setMethod] = useState("");
  const [visibility, setVisibility] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<PaymentPlan | "new" | null>(null);
  const action = useSubmit();
  const { data, error, loading, reload } = useApi(
    () => catalogApi.paymentPlans.list({ program_id: programId, academic_year: year, payment_method: method, visibility, page, size: SIZE }),
    [programId, year, method, visibility, page]);
  const f = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1); };

  async function setStatus(p: PaymentPlan, s: PublicationStatus) {
    if (await action.run(() => catalogApi.paymentPlans.setStatus(p.id, s))) reload();
  }
  async function remove(p: PaymentPlan) {
    if (confirmDelete(`la modalité « ${p.name} »`) && await action.run(() => catalogApi.paymentPlans.remove(p.id))) reload();
  }

  return (
    <>
      <div className="filters">
        <ProgramSelect value={programId} onChange={f(setProgramId)} allLabel="Toutes les formations" />
        <YearSelect value={year} onChange={f(setYear)} allLabel="Toutes les années" />
        <select value={method} onChange={(e) => f(setMethod)(e.target.value)} aria-label="Moyen de paiement">
          <option value="">Tous les moyens de paiement</option>
          {Object.entries(PAYMENT_METHODS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <VisibilitySelect value={visibility} onChange={f(setVisibility)} />
        {canWrite && <button className="btn" onClick={() => setEditing("new")}>+ Nouvelle modalité</button>}
      </div>
      {(error || action.error) && <ErrorBanner error={(action.error ?? error)!} onRetry={error ? reload : undefined} />}
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Formation</th><th>Année</th><th>Modalité</th><th>Échéances</th><th>Moyens</th><th>Validité</th><th>Statut</th><th /></tr></thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id}>
                <td><strong>{p.program_name}</strong><div className="code">{p.school} · {p.program_code}</div></td>
                <td className="nowrap">{p.academic_year}</td>
                <td><strong>{p.name}</strong>{p.discount_percent ? <span className="badge badge-visible" style={{ marginLeft: 6 }}>-{p.discount_percent} %</span> : null}
                  {p.description && <div className="muted small">{p.description}</div>}</td>
                <td className="small">{p.installments.map((i) => (
                  <div key={i.id}>{i.label} : {i.percentage != null ? `${i.percentage} %` : money(i.amount, p.currency)}
                    <span className="muted"> {i.due_date ? `· ${day(i.due_date)}` : i.due_description ? `· ${i.due_description}` : ""}</span></div>
                ))}</td>
                <td className="small">{p.payment_methods.map((m) => PAYMENT_METHODS[m]).join(", ") || "—"}</td>
                <td className="small">{validity(p.valid_from, p.valid_until)}</td>
                <td><StatusBadge visibility={p.visibility} /></td>
                <td className="actions">{canWrite && <>
                  <button className="btn btn-ghost btn-sm" disabled={p.status === "archived"} onClick={() => setEditing(p)}>Modifier</button>
                  <PublicationActions status={p.status} onChange={(s) => setStatus(p, s)} disabled={action.busy} />
                  <button className="btn btn-ghost btn-sm danger" onClick={() => remove(p)}>Supprimer</button>
                </>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="empty">Chargement…</div>}
        {data && data.items.length === 0 && <div className="empty">Aucune modalité de paiement.</div>}
      </div>
      {data && <Pagination page={page} size={SIZE} total={data.total} onChange={setPage} />}
      {editing && <PlanForm plan={editing === "new" ? null : editing} defaultProgram={programId}
                            onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
    </>
  );
}

interface Row { label: string; mode: "percentage" | "amount"; value: string; due_date: string; due_description: string }

const toRow = (i: Installment): Row => ({
  label: i.label, mode: i.percentage != null ? "percentage" : "amount", value: str(i.percentage ?? i.amount),
  due_date: i.due_date ?? "", due_description: i.due_description ?? "",
});

function PlanForm({ plan, defaultProgram, onClose, onSaved }: {
  plan: PaymentPlan | null; defaultProgram: string; onClose: () => void; onSaved: () => void;
}) {
  const [f, setF] = useState({
    program_id: plan?.program_id ?? defaultProgram, academic_year: plan?.academic_year ?? currentAcademicYear(),
    name: plan?.name ?? "", description: str(plan?.description), payment_methods: plan?.payment_methods ?? (["bank_transfer"] as PaymentMethod[]),
    discount_percent: str(plan?.discount_percent), currency: plan?.currency ?? "TND", conditions: str(plan?.conditions),
    position: str(plan?.position ?? 0), valid_from: plan?.valid_from ?? "", valid_until: plan?.valid_until ?? "",
  });
  const [rows, setRows] = useState<Row[]>(plan?.installments.map(toRow) ??
    [{ label: "Paiement unique", mode: "percentage", value: "100", due_date: "", due_description: "À l'inscription" }]);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const setRow = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const { busy, error, run } = useSubmit();

  const allPercent = rows.every((r) => r.mode === "percentage");
  const totalPercent = rows.reduce((n, r) => n + (r.mode === "percentage" ? Number(r.value) || 0 : 0), 0);

  function toggleMethod(m: PaymentMethod) {
    set("payment_methods", f.payment_methods.includes(m) ? f.payment_methods.filter((x) => x !== m) : [...f.payment_methods, m]);
  }

  async function submit() {
    const installments: Installment[] = rows.map((r) => ({
      label: r.label, due_date: blankToNull(r.due_date), due_description: blankToNull(r.due_description),
      percentage: r.mode === "percentage" ? toNumber(r.value) : null, amount: r.mode === "amount" ? toNumber(r.value) : null,
    }));
    const body = {
      academic_year: f.academic_year, name: f.name, description: blankToNull(f.description), payment_methods: f.payment_methods,
      discount_percent: toNumber(f.discount_percent), currency: f.currency.toUpperCase(), conditions: blankToNull(f.conditions),
      position: Number(f.position) || 0, valid_from: blankToNull(f.valid_from), valid_until: blankToNull(f.valid_until), installments,
    };
    if (await run(() => plan ? catalogApi.paymentPlans.update(plan.id, body)
                             : catalogApi.paymentPlans.create({ program_id: f.program_id, ...body }))) onSaved();
  }

  return (
    <FormModal title={plan ? "Modifier la modalité de paiement" : "Nouvelle modalité de paiement"} onClose={onClose}
               onSubmit={submit} busy={busy} error={error} wide>
      {plan?.status === "published" && <p className="full small banner" style={{ margin: 0 }}>Cette modalité est publiée : la modification sera immédiatement visible par les candidats.</p>}
      <Field label="Formation *"><ProgramSelect value={f.program_id} onChange={(v) => set("program_id", v)} required disabled={!!plan} /></Field>
      <Field label="Année universitaire *"><YearSelect value={f.academic_year} onChange={(v) => set("academic_year", v)} required /></Field>
      <Field label="Nom *"><input value={f.name} onChange={(e) => set("name", e.target.value)} required minLength={2} maxLength={150} placeholder="Paiement en 3 tranches" /></Field>
      <Field label="Remise (%)"><input type="number" min={0} max={100} step="0.01" value={f.discount_percent} onChange={(e) => set("discount_percent", e.target.value)} /></Field>
      <Field label="Description" full><input value={f.description} onChange={(e) => set("description", e.target.value)} /></Field>
      <Field label="Moyens de paiement acceptés" full>
        <div className="row">{Object.entries(PAYMENT_METHODS).map(([k, v]) => (
          <label key={k} className="check"><input type="checkbox" checked={f.payment_methods.includes(k as PaymentMethod)} onChange={() => toggleMethod(k as PaymentMethod)} />{v}</label>
        ))}</div>
      </Field>

      <div className="full fieldset">
        <div className="spread"><strong>Échéances</strong>
          {allPercent && <span className={`small ${totalPercent === 100 ? "muted" : ""}`} style={{ color: totalPercent === 100 ? undefined : "var(--err)" }}>
            Total : {totalPercent} % {totalPercent === 100 ? "✓" : "(doit faire 100 %)"}</span>}
        </div>
        {rows.map((r, i) => (
          <div className="row" key={i} style={{ marginTop: 8 }}>
            <input style={{ width: 130 }} value={r.label} onChange={(e) => setRow(i, { label: e.target.value })} placeholder="1re tranche" required aria-label="Libellé" />
            <input type="number" min={0} step="0.01" style={{ width: 100 }} value={r.value} onChange={(e) => setRow(i, { value: e.target.value })} required aria-label="Valeur" />
            <select value={r.mode} onChange={(e) => setRow(i, { mode: e.target.value as Row["mode"] })} aria-label="Unité">
              <option value="percentage">%</option><option value="amount">{f.currency}</option>
            </select>
            <input type="date" value={r.due_date} onChange={(e) => setRow(i, { due_date: e.target.value })} aria-label="Échéance" />
            <input style={{ flex: 1, minWidth: 140 }} value={r.due_description} onChange={(e) => setRow(i, { due_description: e.target.value })} placeholder="ou : À l'inscription" aria-label="Échéance (texte)" />
            <button type="button" className="btn btn-ghost btn-sm danger" disabled={rows.length === 1} onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button type="button" className="btn btn-ghost btn-sm" style={{ marginTop: 8 }} disabled={rows.length >= 12}
                onClick={() => setRows([...rows, { label: `${rows.length + 1}e tranche`, mode: "percentage", value: "", due_date: "", due_description: "" }])}>
          + Ajouter une échéance
        </button>
      </div>

      <Field label="Conditions" full hint="Pénalités de retard, pièces à fournir…"><textarea value={f.conditions} onChange={(e) => set("conditions", e.target.value)} /></Field>
      <Field label="Ordre d'affichage"><input type="number" min={0} max={1000} value={f.position} onChange={(e) => set("position", e.target.value)} /></Field>
      <Field label="Devise"><input value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} maxLength={3} /></Field>
      <ValidityFields from={f.valid_from} until={f.valid_until} academicYear={f.academic_year}
                      onChange={(a, b) => setF((s) => ({ ...s, valid_from: a, valid_until: b }))} />
      {!plan && <p className="full muted small" style={{ margin: 0 }}>Créée en brouillon : utilisez « Publier » pour la rendre officielle.</p>}
    </FormModal>
  );
}
