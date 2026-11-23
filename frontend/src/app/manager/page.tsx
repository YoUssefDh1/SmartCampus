import Link from "next/link";
import Section from "@/components/Section";

export default function ManagerPage() {
  return (
    <>
      <h1>Espace responsable</h1>
      <p className="muted">Structure de l'interface : les données dépendent du rôle (académique IIT/ISB, entretien, direction, administrateur).</p>
      <div className="grid">
        <Link href="/manager/catalog" className="card link-card">
          <div className="card-head"><h3>Catalogue des formations</h3><span className="tag">Disponible</span></div>
          <p className="muted">Formations, spécialités, programmes, matières, conditions d'admission, tarifs et modalités de paiement. API : /catalog</p>
        </Link>
        <Section title="Candidats" text="Liste filtrable par école et statut. API : /candidates" />
        <Section title="Recommandations" text="Confirmer ou ajuster une orientation. API : /candidates/{id}/recommendation" />
        <Section title="Entretiens" text="Synthèse du parcours, QCM, rendez-vous, résultat. API : /appointments" />
        <Section title="Tableau de bord" text="Conversations, préinscriptions, taux de transformation. API : /stats" />
        <Section title="Administration" text="Comptes, rôles, documents sources. API : /admin" />
      </div>
    </>
  );
}
