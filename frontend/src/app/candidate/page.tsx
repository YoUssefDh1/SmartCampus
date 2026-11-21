import Section from "@/components/Section";

export default function CandidatePage() {
  return (
    <>
      <h1>Espace candidat</h1>
      <p className="muted">Structure de l'interface : chaque bloc sera branché à son API (voir contrat SA-5).</p>
      <div className="grid">
        <Section title="Mon dossier" text="Informations personnelles et scolaires. API : /candidates/me" />
        <Section title="Mon profil d'orientation" text="Intérêts, niveau, objectifs construits par le chatbot. API : /candidates/me/profile" />
        <Section title="Mes documents" text="Relevés de notes et pièces. API : /documents" />
        <Section title="Ma préinscription" text="Création et suivi. API : /preregistrations" />
        <Section title="Mon QCM" text="QCM personnalisé avant l'entretien. API : /qcm" />
        <Section title="Mon rendez-vous" text="Entretien, confirmations et rappels. API : /appointments" />
      </div>
    </>
  );
}
