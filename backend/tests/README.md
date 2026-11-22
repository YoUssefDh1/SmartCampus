# Plan de tests des API — catalogue (formations, tarifs, conditions d'admission)

Tâche : *Vérifier le fonctionnement et la fiabilité des API* — tester que les données envoyées sont
correctement enregistrées et récupérées, et contrôler les champs obligatoires, les relations entre
les données, les autorisations d'accès et la gestion des erreurs.

Les tests appellent l'API réelle (FastAPI `TestClient`) branchée sur la vraie base PostgreSQL du
projet (schéma + migration 002 + seed). Ils vérifient la réponse HTTP **et** la ligne écrite en base.

## 1. Couverture

| Module | Ce qui est contrôlé | Tests |
|---|---|---|
| `test_api_persistence.py` | **Enregistrement et récupération** : chaque champ envoyé est relu à l'identique (API de gestion, API publique, ligne SQL) ; accents et arabe ; montants exacts au centime ; dates ; échéances dans l'ordre ; PATCH partiel ; `updated_at` mis à jour ; trace dans `audit_log` avec l'identifiant de requête ; pagination, tri, recherche sans accents ; tentative d'injection SQL sans effet | 11 |
| `test_api_validation.py` | **Champs obligatoires et formats** : 22 champs obligatoires retirés un par un (422, champ cité, rien écrit) ; 40 valeurs invalides (vide, trop long, mauvais type, énumération inconnue, année non consécutive, montant négatif ou à 3 décimales, devise, somme des échéances ≠ 100 %…) ; champ inconnu refusé ; `null` refusé sur un champ obligatoire en PATCH ; règles croisées (dates, moyenne minimale) y compris contre la valeur déjà en base ; paramètres de liste et filtres invalides ; JSON mal formé | 91 |
| `test_api_relations.py` | **Relations entre les données** : formation, école, matière ou formation exigée inexistantes ; spécialité d'une autre formation ; formation qui s'exige elle-même ; élément d'un autre programme ; compteurs dérivés (spécialités, programmes, crédits, utilisation des matières) ; une seule version active ; **suppression en cascade** complète ; **suppression refusée** (409) si utilisé : matière, spécialité, formation exigée par une autre, formation avec préinscriptions — sans cascade partielle ; formation inactive = informations masquées au public | 13 |
| `test_api_permissions.py` | **Autorisations d'accès** : matrice de **28 routes d'écriture** et **16 routes de lecture** × rôles (sans jeton 401 ; candidat, jury, conseiller, visiteur, direction 403) ; rôle vérifié avant l'existence de l'élément ; routes publiques ouvertes ; responsable IIT sans aucun accès à l'ISB (23 appels) ; listes filtrées sur son école même avec `school=ISB` ; direction en lecture seule ; administrateur sur tout ; **JWT** : rôle relu en base, priorité sur le mode démo, jeton expiré / sans expiration / mal signé / compte inconnu / `alg=none` refusés, compte désactivé bloqué immédiatement ; mode démo inactif en production | 67 |
| `test_api_errors.py` | **Gestion des erreurs** : format unique `{error: {code, message, details, request_id}}` et en-tête `X-Request-ID` ; 404 avec message précis par ressource ; 405 ; 409 doublons (code, nom, clé de tarif, casse ignorée) ; élément archivé non modifiable ; publication d'une période terminée refusée ; statut identique sans effet ; **tout ou rien** (aucun champ appliqué, aucune échéance orpheline, aucune trace d'audit après un refus) ; aucune fuite technique (SQL, traceback) ; base indisponible → 503 clair, le reste de l'API répond | 25 |
| `test_catalog.py` | Parcours complets (formations, programmes, tarifs, admission, modalités, publication et validité) | 11 |
| `test_api.py` | Socle : santé, Swagger, format d'erreur, erreur interne sans fuite | 5 |
| **Total** | | **223** |

## 2. Lancer les tests

Prérequis : PostgreSQL lancé (`docker compose up -d`), migrations et seed appliqués.

    cd backend
    .venv\Scripts\Activate.ps1          (Linux / macOS : source .venv/bin/activate)
    pip install -r requirements.txt
    python -m app.db.migrate
    python -m app.db.seed
    python -m pytest -q

Un seul module : `python -m pytest -q tests/test_api_permissions.py` — un seul test : ajouter `-k nom_du_test`.

**Rapport HTML** (à joindre à la tâche Jira) :

    python -m pytest --html=rapport_tests.html --self-contained-html

Le fichier `backend/rapport_tests.html` s'ouvre dans le navigateur (non versionné).

Sans PostgreSQL, les tests du catalogue sont **ignorés** avec le message « PostgreSQL injoignable »
(seuls les 5 tests du socle s'exécutent).

## 3. Règles d'écriture des tests

- Les données créées ont un code `T-xxxxxxxx` (formations, matières) ou un e-mail
  `test-…@smartcampus.test` (comptes) ; la fixture `catalog_cleanup` les supprime à la fin de chaque
  module. Les données du seed ne sont jamais modifiées durablement.
- Les tests sont rejouables : deux exécutions de suite donnent le même résultat.
- Les rôles sont simulés par l'en-tête `X-Dev-Role` (mode démo activé par `conftest.py`) ou par de
  vrais jetons JWT signés avec `JWT_SECRET`.
- Fabriques et vérification du format d'erreur : `tests/helpers.py`.

## 4. Anomalies trouvées par ces tests (corrigées)

| Anomalie | Risque | Correction |
|---|---|---|
| Un jeton JWT **sans date d'expiration** était accepté | Un jeton qui fuit resterait valable à vie | `exp` et `sub` obligatoires (`app/core/security.py`) |
| Le formulaire des tarifs acceptait 3 décimales, la base n'en garde que 2 | Erreur 422 incompréhensible pour le responsable | Pas de saisie à 0,01 (`TuitionManager.tsx`) |
| Les codes avec espace étaient acceptés par les formulaires | Erreur 422 après envoi | Format vérifié dans le navigateur (formations, matières) |

## 5. Vérification manuelle (Swagger)

http://localhost:8000/docs — en mode démo, chaque route `/catalog` affiche un champ `x-dev-role`.

1. `POST /catalog/tuition-fees` sans `x-dev-role` → 401 ; avec `candidate` → 403 ; avec `iit_manager`
   et un `program_id` de l'ISB → 403.
2. Même route, `iit_manager`, corps sans `amount` → 422 avec `details: [{field: "amount"…}]`.
3. Corps correct → 201, `status: "draft"` ; `GET /programs/{id}/tuition` ne le montre pas ;
   `POST /catalog/tuition-fees/{id}/status` `{"status": "published"}` → il apparaît.
4. Recréer le même tarif → 409 avec un message clair.
5. `DELETE /catalog/subjects/{id}` d'une matière utilisée → 409 « utilisé par des programmes pédagogiques ».
