"use client";
import { useState } from "react";
import ErrorBanner from "@/components/ErrorBanner";
import { programsApi } from "@/lib/api/services";
import { useApi } from "@/lib/api/useApi";

export default function ProgramsPage() {
  const { data, error, loading, reload } = useApi(() => programsApi.list());
  const [school, setSchool] = useState("");
  const items = (data?.items ?? []).filter((p) => !school || p.school === school);

  return (
    <>
      <h1>Formations</h1>
      <div className="filters">
        {["", "IIT", "ISB"].map((s) => (
          <button key={s || "all"} className={`btn ${school === s ? "" : "btn-light"}`} onClick={() => setSchool(s)}>{s || "Toutes"}</button>
        ))}
      </div>
      {loading && <p className="muted">Chargement…</p>}
      {error && <ErrorBanner error={error} onRetry={reload} />}
      <div className="grid">
        {items.map((p) => (
          <div className="card" key={p.id}>
            <div className="card-head"><h3>{p.name}</h3><span className="tag">{p.school}</span></div>
            <p className="muted small">{p.level} · {p.duration_years} ans</p>
            <p>{p.description}</p>
            <p className="small"><strong>Admission :</strong> {p.admission}</p>
          </div>
        ))}
      </div>
    </>
  );
}
