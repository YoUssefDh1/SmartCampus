"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import Pagination from "@/components/ui/Pagination";
import { programsApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";
import { CYCLES, LANGUAGES, money } from "@/lib/catalog";

const SIZE = 12;

export default function ProgramsPage() {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [school, setSchool] = useState("");
  const [cycle, setCycle] = useState("");
  const [language, setLanguage] = useState("");
  const [page, setPage] = useState(1);

  // Recherche déclenchée 300 ms après la dernière frappe.
  useEffect(() => {
    const t = setTimeout(() => { setQ(text); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [text]);

  const { data, error, loading, reload } = useApi(
    () => programsApi.list({ q, school, cycle, language, page, size: SIZE }), [q, school, cycle, language, page]);

  const filter = (setter: (v: string) => void) => (v: string) => { setter(v); setPage(1); };

  return (
    <>
      <h1>Formations</h1>
      <p className="muted">Formations de l&apos;IIT et de l&apos;ISB : conditions d&apos;admission, frais et modalités de paiement officiels.</p>

      <div className="filters">
        <input className="search" type="search" placeholder="Rechercher une formation, un métier, un diplôme…"
               value={text} onChange={(e) => setText(e.target.value)} aria-label="Rechercher" />
        {["", "IIT", "ISB"].map((s) => (
          <button key={s || "all"} className={`btn ${school === s ? "" : "btn-light"}`} onClick={() => filter(setSchool)(s)}>
            {s || "Toutes"}
          </button>
        ))}
        <select value={cycle} onChange={(e) => filter(setCycle)(e.target.value)} aria-label="Niveau">
          <option value="">Tous les niveaux</option>
          {Object.entries(CYCLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select value={language} onChange={(e) => filter(setLanguage)(e.target.value)} aria-label="Langue">
          <option value="">Toutes les langues</option>
          {Object.entries(LANGUAGES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      {loading && <p className="muted">Chargement…</p>}
      {error && <ErrorBanner error={error} onRetry={reload} />}
      {data && data.items.length === 0 && <div className="card empty">Aucune formation ne correspond à ces critères.</div>}

      <div className="grid">
        {data?.items.map((p) => (
          <Link href={`/programs/${p.id}`} className="card link-card stack" key={p.id}>
            <div className="card-head"><h3>{p.name}</h3><span className="tag">{p.school}</span></div>
            <p className="muted small" style={{ margin: 0 }}>
              {p.level}{p.duration_years ? ` · ${p.duration_years} an${p.duration_years > 1 ? "s" : ""}` : ""}
              {p.teaching_languages.length ? ` · ${p.teaching_languages.map((l) => l.toUpperCase()).join(" / ")}` : ""}
            </p>
            {p.description && <p style={{ margin: 0 }}>{p.description}</p>}
            <div className="spread" style={{ marginTop: "auto" }}>
              <span className="small">
                {p.tuition_from != null
                  ? <>À partir de <span className="price">{money(p.tuition_from, p.tuition_currency ?? "TND")}</span> / an</>
                  : <span className="muted">Tarifs bientôt disponibles</span>}
              </span>
              <span className="back">Voir la fiche →</span>
            </div>
          </Link>
        ))}
      </div>
      {data && <Pagination page={page} size={SIZE} total={data.total} onChange={setPage} />}
    </>
  );
}
