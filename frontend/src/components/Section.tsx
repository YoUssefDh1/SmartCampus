// Carte simple pour les écrans « coquille » (candidat / responsable).
export default function Section({ title, text, status = "À venir" }: { title: string; text: string; status?: string }) {
  return (
    <div className="card">
      <div className="card-head"><h3>{title}</h3><span className="tag">{status}</span></div>
      <p className="muted">{text}</p>
    </div>
  );
}
