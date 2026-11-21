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

Le backend et le frontend démarrent **sans Docker** : la base n'est utilisée qu'à partir de SA-16.

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
| http://localhost:8000/api/v1/programs | Liste des formations de démonstration |
| http://localhost:3000 | Accueil avec le bandeau vert « Backend connecté » |
| http://localhost:3000/programs | Les 4 formations de démonstration |
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
| frontend/.env.local | NEXT_PUBLIC_API_URL | http://localhost:8000/api/v1 | Adresse de l'API |
| .env (racine) | POSTGRES_USER / PASSWORD / DB / PORT | smartcampus / smartcampus / smartcampus / 5432 | Base Docker |

Ports utilisés : 3000 (frontend), 8000 (backend), 5432 (PostgreSQL).

## 7. Données de démonstration

Dossier `data/demo/` (données fictives) :

| Fichier | Contenu | Utilisé par |
|---|---|---|
| programs.json | 4 formations IIT / ISB | Catalogue (déjà branché : `/programs`) |
| candidates.json | 3 candidats avec profil et recommandations | Base de données (SA-18, Membre 2) |
| users.json | 6 comptes de démo, un par rôle (mot de passe : demo1234) | Authentification (SA-28, Membre 4) |
| conversation_example.json | Conversation en français, tunisien et Arabizi | Tests du chatbot (Membre 5) |

Le catalogue lit ces fichiers tant que la base n'est pas prête. Le Membre 3 remplacera la source dans
`backend/app/services/programs_service.py`.

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
