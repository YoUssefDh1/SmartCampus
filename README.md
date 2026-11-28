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
    ├── docker-compose.yml   Stack complet : PostgreSQL, API et interface
    ├── .env.example         Variables de docker-compose
    └── README.md            Ce guide

## 2. Prérequis

- Git
- Docker Desktop avec Docker Compose
- Ollama installé et lancé sur l'ordinateur qui exécute Docker

Python et Node.js ne sont pas nécessaires pour lancer le projet avec Docker.

## 3. Lancer le projet avec Docker

### Première installation

Clonez le dépôt puis placez-vous dans son dossier :

    git clone https://github.com/YoUssefDh1/SmartCampus.git
    cd SmartCampus

Téléchargez les deux modèles Ollama (une seule fois par ordinateur), puis lancez le projet depuis la racine :

    ollama pull mistral:latest
    ollama pull nomic-embed-text
    docker compose up -d

Docker construit automatiquement les images si elles ne sont pas encore présentes. Le backend applique les migrations, charge les données de démonstration et initialise l'index RAG au premier démarrage.

### Après un `git pull`

Depuis le dossier du projet, reconstruisez et redémarrez les conteneurs pour inclure les changements récupérés :

    git pull
    docker compose up --build -d

Pour simplement redémarrer les conteneurs sans changement de code :

    docker compose up -d

Vérifiez leur état :

    docker compose ps

Attendez que `db` et `backend` soient `healthy`. L'interface est disponible ici :

| Service | URL |
|---|---|
| Base de données PostgreSQL + pgvector | `localhost:5432` |
| Backend FastAPI (migrations, seed et index RAG automatiques) | `http://localhost:8000` |
| Swagger Backend | `http://localhost:8000/docs` |
| Santé Backend | `http://localhost:8000/api/v1/health` |
| Frontend Next.js | `http://localhost:3000` |

Arrêter le projet sans supprimer les données :

    docker compose down

Ne lancez pas `docker compose down -v` si vous voulez conserver l'historique du chat et l'index RAG dans PostgreSQL. Chaque ordinateur possède sa propre base locale.

### Vérifier le RAG dans le chat

1. Attendez que `docker compose ps` affiche `healthy` pour `backend`, puis vérifiez l'index :

       docker compose exec db psql -U smartcampus -d smartcampus -c "SELECT count(*) FROM rag_chunks;"

   Le résultat doit être supérieur à zéro (223 passages avec les documents fournis).
2. Ouvrez `http://localhost:3000`, ouvrez le chat et demandez :
   **« Quels sont les droits d'inscription à l'IIT pour les étudiants tunisiens et internationaux ? »**
3. La réponse doit indiquer **800 DT** et **800 €**, et citer une source avec `[1]`.

Si l'index est vide, consultez les journaux puis relancez l'ingestion :

    docker compose logs backend --tail 50
    docker compose exec backend python -m scripts.ingest_knowledge

## 4. Vérifications

| Adresse | Résultat attendu |
|---|---|
| http://localhost:8000/docs | Swagger avec tous les domaines d'API |
| http://localhost:8000/api/v1/health | `{"status":"ok", ...}` |
| http://localhost:8000/api/v1/programs | Les 4 formations de démonstration (lues dans PostgreSQL) |
| http://localhost:3000 | Accueil avec le bandeau vert « Backend connecté » |
| http://localhost:3000/programs | Les 4 formations de démonstration, recherche et filtres |
| http://localhost:3000/programs/{id} | Fiche : spécialités, admission, frais, modalités de paiement, programme |
| http://localhost:3000/manager/catalog | Gestion du catalogue (mode démo : choisir le rôle en haut de page) |
| http://localhost:3000/chat | Chat IA avec réponses basées sur les sources RAG |

## 5. Configuration Docker (optionnelle)

Aucun fichier `.env` n'est nécessaire pour le lancement local : Compose utilise les valeurs par défaut de démonstration. Pour modifier l'utilisateur, le mot de passe, le nom ou le port publié de PostgreSQL, copiez `.env.example` à la racine en `.env`, puis modifiez ses valeurs. Le backend continue à joindre PostgreSQL sur le réseau Docker interne (`db:5432`).

Ports utilisés par défaut : 3000 (interface), 8000 (API), 5432 (PostgreSQL).

## 6. Données de démonstration

Dossier `data/demo/` (données fictives) :

| Fichier | Contenu | Utilisé par |
|---|---|---|
| programs.json | 4 formations IIT / ISB | Plus utilisé : le catalogue est dans PostgreSQL (`seed.sql`) |
| candidates.json | 3 candidats avec profil et recommandations | Base de données (SA-18, Membre 2) |
| users.json | 6 comptes de démo, un par rôle (mot de passe : demo1234) | Authentification (SA-28, Membre 4) |
| conversation_example.json | Conversation en français, tunisien et Arabizi | Tests du chatbot (Membre 5) |

Le catalogue (formations, spécialités, programmes, matières, admission, frais, modalités de paiement) est
chargé automatiquement dans PostgreSQL au démarrage du backend (section « Catalogue de DEMONSTRATION » de `seed.sql`).
Les montants et conditions sont fictifs : à remplacer par les informations officielles.

## 7. Problèmes fréquents

| Symptôme | Cause probable | Solution |
|---|---|---|
| Bandeau rouge « Impossible de joindre le serveur » | Backend arrêté ou en cours de démarrage | Vérifier `docker compose ps`, puis `docker compose logs backend --tail 50` |
| Chat indique que l'assistant IA est indisponible | Ollama ou un modèle requis n'est pas prêt | Démarrer Ollama, vérifier `ollama list`, puis exécuter `ollama pull mistral:latest` et `ollama pull nomic-embed-text` |
| Index RAG vide ou non initialisé | L'ingestion initiale n'a pas abouti | Vérifier les logs backend, puis lancer `docker compose exec backend python -m scripts.ingest_knowledge` |
| `docker compose` échoue | Docker Desktop non lancé | Lancer Docker Desktop puis réessayer |
| Port déjà utilisé | Un autre programme utilise le port 3000, 8000 ou 5432 | Arrêter l'autre programme ou modifier le port concerné dans le `.env` racine. Le port interne PostgreSQL reste `5432`. |

## 8. Règles de travail en équipe

- Branches : `main` (stable), `develop` (intégration), `feature/SA-xx-nom` (une par tâche).
- Pull Request obligatoire vers `develop`, relue par un autre membre.
- Messages de commit : `SA-7: init FastAPI`.
- Ne jamais versionner `.env`, `.env.local`, `.venv`, `node_modules`.
- Contrat d'API : voir le document SA-5 ; Swagger (`/docs`) fait foi pour les routes déjà codées.

## 9. Catalogue : formations, tarifs et conditions d'admission (SA-20 / SA-21)

### Base de données
La migration `backend/migrations/002_catalog_publication_payment.sql` est appliquée automatiquement au démarrage
du backend Docker et complète le schéma sans le modifier :

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
Après avoir lancé le stack Docker, exécutez les tests backend avec :

    docker compose exec backend python -m pytest -q

Les tests du catalogue utilisent la base Docker migrée et seedée.
