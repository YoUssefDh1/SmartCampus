import Link from "next/link";

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
      <path d="M4.25 10h11.5m-4.5-4.5 4.5 4.5-4.5 4.5" />
    </svg>
  );
}

function ActionIcon({ type }: { type: "book" | "chat" }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none">
      {type === "book" ? (
        <>
          <path d="M4.5 5.75A2.25 2.25 0 0 1 6.75 3.5H20v16H6.75a2.25 2.25 0 0 0-2.25 2.25v-16Z" />
          <path d="M4.5 18.5A2.5 2.5 0 0 1 7 16h13M8.5 8h7M8.5 11h7" />
        </>
      ) : (
        <>
          <path d="M20.5 11.5a7.5 7.5 0 0 1-7.5 7.5H7l-3.5 2v-5A7.5 7.5 0 1 1 20.5 11.5Z" />
          <path d="M8 11.5h8M8 8.5h5" />
        </>
      )}
    </svg>
  );
}

export default function Home() {
  return (
    <div className="home">
      <section className="home-hero">
        <div className="home-copy">
          <p className="eyebrow"><span className="eyebrow-mark" />Orientation universitaire · IIT &amp; ISB</p>
          <h1>Un choix d&apos;études plus clair <span>commence ici.</span></h1>
          <p className="home-intro">
            Explorez les formations de l&apos;IIT et de l&apos;ISB, consultez les informations disponibles
            et échangez avec l&apos;assistant d&apos;orientation.
          </p>
          <div className="hero-actions">
            <Link href="/programs" className="btn btn-primary">
              Explorer les formations <ArrowIcon />
            </Link>
            <Link href="/chat" className="btn btn-secondary">
              Discuter avec l&apos;assistant
            </Link>
          </div>
          <p className="home-note">Le catalogue présente les informations publiées par les établissements.</p>
        </div>

        <aside className="explore-panel" aria-label="Informations à explorer">
          <div className="explore-panel-head">
            <span className="panel-kicker">POUR BIEN COMMENCER</span>
            <span className="panel-spark" aria-hidden="true">✦</span>
          </div>
          <h2>Les détails qui comptent, au même endroit.</h2>
          <p>Parcourez les informations publiées pour chaque formation.</p>
          <ul className="explore-list">
            <li><span>01</span><span>Parcours et programmes</span></li>
            <li><span>02</span><span>Conditions d&apos;admission</span></li>
            <li><span>03</span><span>Frais et modalités de paiement</span></li>
          </ul>
          <Link href="/programs" className="panel-link">
            Voir le catalogue <ArrowIcon />
          </Link>
        </aside>
      </section>

      <section className="home-section" aria-labelledby="home-actions-title">
        <div className="home-section-heading">
          <div>
            <p className="eyebrow">VOTRE PROCHAIN PAS</p>
            <h2 id="home-actions-title">Par où souhaitez-vous commencer ?</h2>
          </div>
          <p>Choisissez le chemin qui vous convient.</p>
        </div>
        <div className="home-action-grid">
          <Link href="/programs" className="home-action-card">
            <span className="home-card-icon"><ActionIcon type="book" /></span>
            <span className="home-card-kicker">LE CATALOGUE</span>
            <h3>Explorer les formations</h3>
            <p>Comparez les parcours et consultez les informations disponibles.</p>
            <span className="home-card-link">Découvrir <ArrowIcon /></span>
          </Link>
          <Link href="/chat" className="home-action-card">
            <span className="home-card-icon"><ActionIcon type="chat" /></span>
            <span className="home-card-kicker">L&apos;ASSISTANT</span>
            <h3>Poser vos questions</h3>
            <p>Échangez pour préciser vos intérêts et explorer vos options.</p>
            <span className="home-card-link">Ouvrir le chat <ArrowIcon /></span>
          </Link>
        </div>
      </section>

      <div className="home-audience-links">
        <span>Vous avez déjà un espace ?</span>
        <Link href="/candidate">Espace candidat <ArrowIcon /></Link>
        <Link href="/manager">Espace responsable <ArrowIcon /></Link>
      </div>
    </div>
  );
}
