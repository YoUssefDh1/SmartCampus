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

## Ollama (LLM local)

Installez Ollama sur la machine qui exécutera le modèle, puis téléchargez un
modèle à comparer :

    ollama pull gemma3:4b
    ollama pull qwen3:8b
    ollama pull minicpm-v:latest
    ollama pull mistral:latest

Configurez `LLM_MODEL` dans `backend/.env` pour le modèle installé, par exemple
`gemma3:4b` ou `qwen3:8b`. Le backend appelle l'API Ollama locale à
`http://localhost:11434`; modifiez `LLM_BASE_URL` si Ollama tourne ailleurs.
Les sessions sont actuellement conservées en mémoire et seront perdues au
redémarrage du backend. Les appels au modèle nécessitent qu'Ollama soit lancé.

## RAG sur les sources officielles IIT/ISB

Le RAG utilise PostgreSQL/pgvector et un modèle d'embeddings Ollama séparé du
modèle de chat. Placez les documents officiels vérifiés (PDF texte, Markdown ou
texte UTF-8) dans `data/knowledge_base/`.

Depuis la racine du dépôt, lancez PostgreSQL :

    docker compose up -d

Puis depuis `backend/`, lancez Ollama et ingérez les sources :

    ollama pull nomic-embed-text
    python -m scripts.ingest_knowledge

Activez ensuite `RAG_ENABLED=true` dans `backend/.env` et redémarrez l'API.
`RAG_EMBEDDING_MODEL` choisit le modèle d'embeddings; `LLM_MODEL` reste libre
pour Gemma, Qwen ou un autre modèle Ollama. L'ingestion crée/actualise la table
pgvector `rag_chunks`. Si le RAG est activé sans base ou sans passages pertinents,
le backend signale l'indisponibilité ou demande une confirmation officielle au
lieu d'inventer une réponse. Après avoir changé `RAG_EMBEDDING_MODEL`, réingérez
tous les documents afin que les vecteurs de la base correspondent au modèle.



## Gestion des documents officiels

Les modèles partagés par type de document sont dans
[`backend/docs/document-templates/`](./docs/document-templates/). Ils restent
hors du dossier d'ingestion RAG; n'ingérez que les copies complétées et vérifiées.

Les routes `/api/v1/documents` sont réservées aux responsables IIT/ISB et à
l'administration pour l'écriture; la direction peut consulter. Elles acceptent
des fichiers PDF, Markdown et texte UTF-8. Un nouveau document est créé en
brouillon; une nouvelle version importée reste inactive jusqu'à sa publication.
Publiez une version avec
`POST /api/v1/documents/{id}/versions/{version_id}/publish`; le retrait par
`DELETE /api/v1/documents/{id}` est logique et conserve l'historique.

Les fichiers sont stockés sur disque, tandis que PostgreSQL conserve les
métadonnées et le chemin relatif du fichier. `DOCUMENTS_STORAGE_DIR` configure
le répertoire (par défaut `backend/data/official_documents`) et
`DOCUMENT_MAX_UPLOAD_BYTES` fixe la limite (10 Mio par défaut). Le répertoire
est exclu de Git. Si plusieurs membres exécutent des backends séparés avec la
même base, ils doivent aussi partager ce répertoire ou le monter depuis un
stockage commun; la base seule ne transporte pas les fichiers.

En mode développement, les écritures exigent un compte du personnel existant :
utilisez un jeton de connexion ou `X-Dev-Role` avec `X-Dev-User-Id`.

La gestion des fichiers par API n'alimente pas encore automatiquement le RAG.
L'ingestion existante continue de lire `RAG_DOCUMENTS_DIR` via
`python -m scripts.ingest_knowledge`.

## Évaluation comparative des modèles (SA-31–33)

Le jeu d'évaluation et le barème sont dans `data/llm_eval/`. Pour exécuter les
mêmes questions sur les deux modèles avec Ollama :

    ollama pull gemma3:4b
    ollama pull qwen3:4b
    ollama pull minicpm-v:latest
    ollama pull mistral:latest
    python scripts/benchmark_llm.py

Le rapport JSON conserve les réponses brutes, les mesures de latence et de
débit, ainsi que des champs de notation humaine. Complétez la revue selon
`data/llm_eval/README.md`; le script ne choisit pas automatiquement le meilleur
modèle. Les résultats locaux sont ignorés par Git.

Pour tester le modèle configuré via le parcours FastAPI (réponses réelles,
code-switching et mémoire entre tours), Ollama et PostgreSQL doivent être lancés.
Le test crée une vraie session visiteur et utilise PostgreSQL pour conserver
l'historique; Uvicorn n'a pas besoin d'être démarré.

Depuis la racine du dépôt, démarrez la base :

    docker compose up -d db

Puis, depuis `backend/`, appliquez le schéma et le seed avant de lancer le test :

    python -m app.db.migrate
    python -m app.db.seed

    $env:RUN_LLM_INTEGRATION="1"
    python -m pytest -q tests/integration/test_live_ollama.py

Le test appelle le modèle configuré par `LLM_MODEL`. Sans le drapeau
`RUN_LLM_INTEGRATION=1`, il est ignoré pendant les tests habituels. La détection
de langue actuelle est une heuristique conservatrice à valider et à ajuster
avec les résultats du jeu Tunisien/Arabizi; elle ne remplace pas l'évaluation
humaine.

## Tests
    python -m pytest -q

Les tests du catalogue (tests/test_catalog.py) ont besoin de PostgreSQL migré et seedé ; sinon ils sont ignorés.

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
                             programs.py (public), catalog.py + catalog_pricing.py (gestion du catalogue)
    app/schemas/             schémas Pydantic (entrées / sorties)
    app/services/            logique métier (appelée par les routes)
                             catalog_service, tuition_admission_service, programs_service, db_utils
    app/models/  app/db/     base de données (Membre 2)
    app/agents/              agents LangGraph (Membre 5)

## Règle d'équipe
Une route reste fine : elle valide, appelle un service, renvoie le résultat.
Les erreurs se lèvent avec `AppError` (voir app/core/errors.py) :
    raise NotFoundError("Dossier introuvable.")
