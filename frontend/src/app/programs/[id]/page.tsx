"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import ErrorBanner from "@/components/ErrorBanner";
import { programsApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import {
  FEE_TYPES, LANGUAGES, PAYMENT_METHODS, REQUIREMENT_CATEGORIES, REQUIREMENT_KINDS, day, money, validity,
} from "@/lib/catalog";
import type { AdmissionRequirementPublic, Installment, ProgramCurriculum } from "@/types/api";

export default function ProgramDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: p, error, loading, reload } = useApi(() => programsApi.get(id), [id]);
  const curriculum = useApi(() => programsApi.curriculum(id), [id]);

  if (loading) return <p className="muted">Chargement…</p>;
  if (error || !p) return (<><Link href="/programs" className="back">← Toutes les formations</Link>{error && <ErrorBanner error={error} onRetry={reload} />}</>);

  const byCategory = (cat: string) => p.admission_requirements.filter((r) => r.category === cat);

  return (
    <>
      <Link href="/programs" className="back">← Toutes les formations</Link>
      <div className="hero" style={{ marginTop: 10 }}>
        <div>
          <div className="row"><span className="tag">{p.school}</span><span className="tag">{p.level}</span></div>
          <h1 style={{ marginTop: 8 }}>{p.name}</h1>
          <p className="muted" style={{ margin: 0 }}>{p.institution_name} · <span className="code">{p.code}</span></p>
        </div>
        {p.tuition_from != null && (
          <div className="card" style={{ textAlign: "right" }}>
            <div className="muted small">Frais de scolarité à partir de</div>
            <div className="kpi">{money(p.tuition_from, p.tuition_currency ?? "TND")}</div>
          </div>
        )}
      </div>

      <div className="grid">
        <Info label="Durée" value={p.duration_years ? `${p.duration_years} an${p.duration_years > 1 ? "s" : ""}` : "—"} />
        <Info label="Diplôme" value={p.degree ?? "—"} />
        <Info label="Capacité d'accueil" value={p.capacity != null ? `${p.capacity} places` : "—"} />
        <Info label="Langues d'enseignement" value={p.teaching_languages.map((l) => LANGUAGES[l] ?? l).join(", ") || "—"} />
      </div>

      {p.description && <section className="section"><h2>Présentation</h2><p>{p.description}</p></section>}
      {p.career_outcomes && <section className="section"><h2>Débouchés</h2><p>{p.career_outcomes}</p></section>}

      {p.specialties.length > 0 && (
        <section className="section">
          <h2>Spécialités</h2>
          <div className="grid">
            {p.specialties.map((s) => (
              <div className="card" key={s.id}><h3>{s.name}</h3>{s.description && <p className="muted small">{s.description}</p>}</div>
            ))}
          </div>
        </section>
      )}

      <section className="section">
        <h2>Conditions d&apos;admission</h2>
        {p.admission_requirements.length === 0 && <p className="muted">Les conditions officielles ne sont pas encore publiées.</p>}
        <div className="grid">
          {(["admission", "prerequisite"] as const).map((cat) => byCategory(cat).length > 0 && (
            <div className="card" key={cat}>
              <h4>{cat === "admission" ? "Critères" : REQUIREMENT_CATEGORIES[cat]}</h4>
              <ul className="list">{byCategory(cat).map((r) => <Requirement key={r.id} r={r} />)}</ul>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <h2>Frais de scolarité</h2>
        {p.tuition_fees.length === 0 ? <p className="muted">Les tarifs officiels ne sont pas encore publiés.</p> : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="table">
              <thead><tr><th>Année</th><th>Frais</th><th>Niveau</th><th style={{ textAlign: "right" }}>Montant</th><th>Validité</th></tr></thead>
              <tbody>
                {p.tuition_fees.map((f) => (
                  <tr key={f.id}>
                    <td>{f.academic_year}</td>
                    <td>{FEE_TYPES[f.fee_type]}{f.description && <div className="muted small">{f.description}</div>}</td>
                    <td>{f.study_year ? `${f.study_year}e année` : "Toutes"}</td>
                    <td style={{ textAlign: "right" }} className="price">{money(f.amount, f.currency)}</td>
                    <td className="small">{validity(f.valid_from, f.valid_until)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {p.payment_plans.length > 0 && (
        <section className="section">
          <h2>Modalités de paiement</h2>
          <div className="grid">
            {p.payment_plans.map((plan) => (
              <div className="card stack" key={plan.id}>
                <div className="card-head">
                  <h3>{plan.name}</h3>
                  {plan.discount_percent ? <span className="badge badge-visible">-{plan.discount_percent} %</span> : null}
                </div>
                {plan.description && <p className="muted small" style={{ margin: 0 }}>{plan.description}</p>}
                <div className="timeline">
                  {plan.installments.map((i) => <Step key={i.id ?? i.label} i={i} currency={plan.currency} />)}
                </div>
                {plan.payment_methods.length > 0 && (
                  <div className="chips">{plan.payment_methods.map((m) => <span key={m} className="tag">{PAYMENT_METHODS[m]}</span>)}</div>
                )}
                {plan.conditions && <p className="small muted" style={{ margin: 0 }}>{plan.conditions}</p>}
                <p className="small muted" style={{ margin: 0 }}>{plan.academic_year} · {validity(plan.valid_from, plan.valid_until)}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <CurriculumSection data={curriculum.data} />

      <p className="muted small section">
        Seules les informations publiées et en vigueur à ce jour sont affichées. Pour toute question,
        posez-la à <Link href="/chat" className="back">l&apos;assistant</Link>.
      </p>
    </>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <div className="card"><div className="muted small">{label}</div><strong>{value}</strong></div>;
}

function Requirement({ r }: { r: AdmissionRequirementPublic }) {
  return (
    <li>
      <span className="dot" />
      <div>
        <div>{r.description}{!r.is_mandatory && <span className="muted small"> (souhaité)</span>}</div>
        <div className="muted small">
          {REQUIREMENT_KINDS[r.kind]}
          {r.min_average != null && ` · ${r.min_average}/20 minimum`}
          {r.required_program_id && r.required_program_name && <> · <Link className="back" href={`/programs/${r.required_program_id}`}>{r.required_program_name}</Link></>}
        </div>
        {r.accepted_bac_series && r.accepted_bac_series.length > 0 && (
          <div className="chips" style={{ marginTop: 4 }}>{r.accepted_bac_series.map((s) => <span key={s} className="tag">{s}</span>)}</div>
        )}
      </div>
    </li>
  );
}

function Step({ i, currency }: { i: Installment; currency: string }) {
  return (
    <div className="step">
      <strong>{i.label}</strong>
      <div>{i.percentage != null ? `${i.percentage} %` : money(i.amount, currency)}</div>
      <div className="muted small">{i.due_date ? `Avant le ${day(i.due_date)}` : i.due_description ?? ""}</div>
    </div>
  );
}

function CurriculumSection({ data }: { data: ProgramCurriculum | null }) {
  if (!data || data.curricula.length === 0) return null;
  return (
    <section className="section">
      <h2>Programme pédagogique</h2>
      {data.curricula.map((c) => (
        <div key={c.id} className="section">
          <h4>{c.specialty_name ?? "Tronc commun"} · {c.academic_year}{c.total_credits ? ` · ${c.total_credits} crédits` : ""}</h4>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Année</th><th>Semestre</th><th>Matière</th><th>Coef.</th><th>Crédits</th></tr></thead>
              <tbody>
                {c.subjects.map((s) => (
                  <tr key={s.id}>
                    <td>{s.study_year}</td><td>S{s.semester}</td>
                    <td>{s.subject_name} <span className="code">{s.subject_code}</span>{!s.is_mandatory && <span className="muted small"> · optionnelle</span>}</td>
                    <td>{s.coefficient ?? "—"}</td><td>{s.credits ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
