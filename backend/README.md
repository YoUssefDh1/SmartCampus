# SmartCampus AI - Backend (FastAPI)

## Lancer
    python -m venv .venv
    source .venv/bin/activate        # Windows : .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env
    uvicorn app.main:app --reload

- Swagger : http://localhost:8000/docs
- ReDoc   : http://localhost:8000/redoc
- Santé   : http://localhost:8000/api/v1/health

## Tests
    python -m pytest -q

## PostgreSQL
Depuis la racine du dépôt, démarrer PostgreSQL avec `docker compose up -d`.
Depuis le dossier `backend` (environnement Python activé), appliquer le schéma et charger
les données de démonstration :

    python -m app.db.migrate
    python -m app.db.seed

Les modifications de schéma ultérieures doivent être ajoutées comme fichiers SQL numérotés
dans `backend/migrations/`; une migration déjà appliquée ne doit pas être modifiée.

## Structure
    app/main.py              création de l'application
    app/core/                config, erreurs, middleware, rôles
    app/api/v1/endpoints/    routes par domaine (une par membre)
    app/schemas/             schémas Pydantic (entrées / sorties)
    app/services/            logique métier (appelée par les routes)
    app/models/  app/db/     base de données (Membre 2)
    app/agents/              agents LangGraph (Membre 5)

## Règle d'équipe
Une route reste fine : elle valide, appelle un service, renvoie le résultat.
Les erreurs se lèvent avec `AppError` (voir app/core/errors.py) :
    raise NotFoundError("Dossier introuvable.")
