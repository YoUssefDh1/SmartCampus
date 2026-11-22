# SmartCampus AI

Plateforme agentique d'orientation universitaire (IIT / ISB) - Projet IA générative 2026-2027.

## 1. Contenu du dépôt

    smartcampus-ai/
    ├── backend/             API FastAPI (Python)              -> http://localhost:8000
    ├── frontend/            Interface Next.js (React)          -> http://localhost:3000
    ├── data/demo/           Données de démonstration (JSON)
    ├── schema.sql           Schéma initial versionné (tables, relations, fonctions)
    ├── seed.sql              Données de démonstration reproductibles
    ├── docker/init.sql      Active pgvector dans PostgreSQL
    ├── docker-compose.yml   Base PostgreSQL + pgvector         -> localhost:5432
    ├── .env.example         Variables de docker-compose
    └── README.md            Ce guide

## 2. Prérequis

| Outil | Version | Vérifier | Obligatoire |
|---|---|---|---|
| Python | 3.11 ou plus | `python --version` | Oui |
| Node.js | 20 ou plus | `node --version` | Oui |
| Git | récent | `git --version` | Oui |
| Docker Desktop | récent | `docker --version` | Pour la base de données (Membre 2) |

Le backend et le frontend démarrent **sans Docker**, mais le catalogue (`/programs`, `/catalog`, pages Formations
et Catalogue) lit PostgreSQL : lancer la base (section 3.3) pour l'utiliser.

## 3. Installation

### 3.1 Backend

Windows (PowerShell) :

    cd backend
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env

Linux / macOS :

    cd backend
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env

Si PowerShell refuse d'activer l'environnement :
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, puis relancer.

### 3.2 Frontend

    cd frontend
    npm install
    copy .env.local.example .env.local      (Linux / macOS : cp .env.local.example .env.local)

### 3.3 Base de données

    copy .env.example .env                  (à la racine ; Linux / macOS : cp)
    docker compose up -d
    docker compose ps                       (le service "db" doit être "healthy")

Puis, depuis le dossier `backend` avec l'environnement Python activé :

    pip install -r requirements.txt
    copy .env.example .env                  (Linux / macOS : cp .env.example .env)
    python -m app.db.migrate
    python -m app.db.seed

Les migrations SQL versionnées sont appliquées une seule fois et leur empreinte est vérifiée.
Pour faire évoluer le schéma, ajouter un fichier SQL numéroté dans `backend/migrations/` ;
ne pas modifier une migration déjà appliquée. Le seed est réexécutable sans ajouter de doublons.
Le volume PostgreSQL reste local à chaque développeur et n'est pas commité.

## 4. Démarrage

Ouvrir **deux terminaux**.

Terminal 1 - Backend (dossier `backend`, environnement activé) :

    uvicorn app.main:app --reload

Terminal 2 - Frontend (dossier `frontend`) :

    npm run dev

## 5. Vérifications

| Adresse | Résultat attendu |
|---|---|
| http://localhost:8000/docs | Swagger avec tous les domaines d'API |
| http://localhost:8000/api/v1/health | `{"status":"ok", ...}` |
| http://localhost:8000/api/v1/programs | Les 4 formations de démonstration (lues dans PostgreSQL) |
| http://localhost:3000 | Accueil avec le bandeau vert « Backend connecté » |
| http://localhost:3000/programs | Les 4 formations de démonstration, recherche et filtres |
| http://localhost:3000/programs/{id} | Fiche : spécialités, admission, frais, modalités de paiement, programme |
| http://localhost:3000/manager/catalog | Gestion du catalogue (mode démo : choisir le rôle en haut de page) |
| http://localhost:3000/chat | Chat : l'envoi d'un message affiche « pas encore disponible » (normal) |

Tests automatiques du backend : `python -m pytest -q` (dans `backend`, environnement activé).

## 6. Paramètres de configuration

| Fichier | Variable | Valeur par défaut | Rôle |
|---|---|---|---|
| backend/.env | ENVIRONMENT | development | Environnement d'exécution |
| backend/.env | CORS_ORIGINS | ["http://localhost:3000"] | Origines autorisées à appeler l'API |
| backend/.env | DATABASE_URL | postgresql+psycopg://smartcampus:smartcampus@localhost:5432/smartcampus | Connexion PostgreSQL |
| backend/.env | JWT_SECRET | change-me | Secret des jetons (à changer hors démo) |
| backend/.env | ACCESS_TOKEN_MINUTES | 30 | Durée du jeton |
| backend/.env | AUTH_DEV_MODE | true (exemple) | Mode démo : l'en-tête X-Dev-Role simule un rôle tant que /auth/login n'existe pas (ignoré hors development) |
| frontend/.env.local | NEXT_PUBLIC_API_URL | http://localhost:8000/api/v1 | Adresse de l'API |
| .env (racine) | POSTGRES_USER / PASSWORD / DB / PORT | smartcampus / smartcampus / smartcampus / 5432 | Base Docker |

Ports utilisés : 3000 (frontend), 8000 (backend), 5432 (PostgreSQL).

## 7. Données de démonstration

Dossier `data/demo/` (données fictives) :

| Fichier | Contenu | Utilisé par |
|---|---|---|
| programs.json | 4 formations IIT / ISB | Plus utilisé : le catalogue est dans PostgreSQL (`seed.sql`) |
| candidates.json | 3 candidats avec profil et recommandations | Base de données (SA-18, Membre 2) |
| users.json | 6 comptes de démo, un par rôle (mot de passe : demo1234) | Authentification (SA-28, Membre 4) |
| conversation_example.json | Conversation en français, tunisien et Arabizi | Tests du chatbot (Membre 5) |

Le catalogue (formations, spécialités, programmes, matières, admission, frais, modalités de paiement) est
chargé dans PostgreSQL par `python -m app.db.seed` (section « Catalogue de DEMONSTRATION » de `seed.sql`).
Les montants et conditions sont fictifs : à remplacer par les informations officielles.

## 8. Problèmes fréquents

| Symptôme | Cause probable | Solution |
|---|---|---|
| Bandeau rouge « Impossible de joindre le serveur » | Backend arrêté | Lancer `uvicorn app.main:app --reload` |
| Erreur CORS dans la console du navigateur | Frontend ouvert sur un autre port | Ajouter l'adresse dans CORS_ORIGINS (backend/.env) |
| `Address already in use` | Port 8000 ou 3000 occupé | Fermer l'autre programme ou changer de port |
| `uvicorn` introuvable | Environnement Python non activé | Activer `.venv` (section 3.1) |
| `docker compose` échoue | Docker Desktop non lancé | Lancer Docker Desktop puis réessayer |
| Port 5432 déjà utilisé | PostgreSQL local installé | Changer POSTGRES_PORT dans le `.env` racine et utiliser le même port dans `backend/.env` (`DATABASE_URL`) |

## 9. Règles de travail en équipe

- Branches : `main` (stable), `develop` (intégration), `feature/SA-xx-nom` (une par tâche).
- Pull Request obligatoire vers `develop`, relue par un autre membre.
- Messages de commit : `SA-7: init FastAPI`.
- Ne jamais versionner `.env`, `.env.local`, `.venv`, `node_modules`.
- Contrat d'API : voir le document SA-5 ; Swagger (`/docs`) fait foi pour les routes déjà codées.

## 10. Catalogue : formations, tarifs et conditions d'admission (SA-20 / SA-21)

### Base de données
La migration `backend/migrations/002_catalog_publication_payment.sql` (appliquée par `python -m app.db.migrate`)
complète le schéma sans le modifier :

| Ajout | Rôle |
|---|---|
| `status` (draft / published / archived), `valid_from`, `valid_until`, `published_at`, `published_by_id` sur `tuition_fee` et `admission_requirement` | Statut de publication et période de validité |
| Tables `payment_plan` + `payment_installment` | Modalités de paiement (moyens acceptés, remise, échéances en % ou en montant) |
| Fonction `catalog_is_official()` + vues `v_official_tuition_fee`, `v_official_admission_requirement`, `v_official_payment_plan` | Règle unique : **publié ET valide aujourd'hui ET formation active** |
| Extension `unaccent` + `catalog_search_text()` | Recherche insensible aux accents (« genie » trouve « Génie ») |

### API (Swagger : http://localhost:8000/docs)
| Public (sans connexion) — candidats, visiteurs, agent IA | Informations officielles uniquement |
|---|---|
| `GET /programs?q=&school=&level=&cycle=&language=&page=&size=` | Recherche et filtres |
| `GET /programs/{id}` | Fiche complète : spécialités, admission, frais, modalités |
| `GET /programs/{id}/tuition?academic_year=` | Frais de scolarité et modalités de paiement en vigueur |
| `GET /programs/{id}/admission?academic_year=` | Conditions d'admission et prérequis en vigueur |
| `GET /programs/{id}/curriculum?academic_year=` | Programmes pédagogiques actifs et matières |

| Gestion (`/catalog`) — responsables IIT / ISB (leur école), admin (tout), direction (lecture) | |
|---|---|
| `/catalog/programs` (+ `/{id}/specialties`), `/catalog/specialties` | Formations, spécialités : GET (filtres), POST, PATCH, DELETE |
| `/catalog/curricula` (+ `/{id}/subjects`, `/{id}/duplicate`), `/catalog/subjects` | Programmes pédagogiques, matières |
| `/catalog/admission-requirements`, `/catalog/tuition-fees`, `/catalog/payment-plans` | CRUD + `POST /{id}/status` (publier, dépublier, archiver) ; filtres `status`, `visibility`, `valid_on`, `academic_year` |

Règles : un élément est créé en **brouillon** ; « Publier » le rend officiel pendant sa période de validité
(refusé si la période est déjà terminée) ; un élément **archivé** n'est plus modifiable (le remettre en brouillon).
Chaque écriture est tracée dans `audit_log`. Les erreurs de la base sont traduites en messages clairs (409 doublon,
409 suppression d'un élément utilisé, 422 règle non respectée).

### Authentification (en attendant SA-28)
Les routes `/catalog` lisent un jeton JWT (`sub` = id app_user, `role`) dès que /auth/login existera.
D'ici là, avec `AUTH_DEV_MODE=true` et `ENVIRONMENT=development`, l'en-tête `X-Dev-Role`
(`admin`, `iit_manager`, `isb_manager`, `direction`) simule un rôle ; la page `/manager/catalog` propose ce choix.
Mettre `AUTH_DEV_MODE=false` dès que la connexion est livrée.

### Pour l'agent IA (Membre 5)
Utiliser `programs_service.get_program_detail(conn, program_id)` ou les fonctions `official_*` de
`tuition_admission_service`, ou les vues `v_official_*` : jamais les tables `tuition_fee`,
`admission_requirement`, `payment_plan` directement (elles contiennent les brouillons).

### Tests
`python -m pytest -q` (dans `backend`) : les tests du catalogue utilisent la base de `DATABASE_URL`
(migrée et seedée) et sont ignorés si elle est injoignable.
