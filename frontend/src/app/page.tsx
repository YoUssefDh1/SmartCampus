import Link from "next/link";
import BackendStatus from "@/components/BackendStatus";

export default function Home() {
  return (
    <>
      <h1>SmartCampus AI</h1>
      <p className="muted">Votre assistant d'orientation pour les formations de l'IIT et de l'ISB.</p>
      <BackendStatus />
      <div className="grid">
        <Link href="/chat" className="card link-card"><h3>Discuter avec l'assistant</h3><p className="muted">Posez vos questions, texte ou vocal.</p></Link>
        <Link href="/programs" className="card link-card"><h3>Découvrir les formations</h3><p className="muted">Licence, Préparatoire, Ingénierie.</p></Link>
        <Link href="/candidate" className="card link-card"><h3>Espace candidat</h3><p className="muted">Dossier, préinscription, QCM, rendez-vous.</p></Link>
        <Link href="/manager" className="card link-card"><h3>Espace responsable</h3><p className="muted">Candidats, recommandations, entretiens.</p></Link>
      </div>
    </>
  );
}
