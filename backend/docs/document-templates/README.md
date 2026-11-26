# Modèles de documents officiels IIT/ISB

Utilisez ces modèles pour structurer les informations recueillies sur les sites
officiels. Les catégories correspondent aux valeurs `doc_type` de l'API :
`brochure`, `regulation`, `curriculum`, `admission_conditions`,
`equivalence_rules` et `other`.

## Comment les utiliser

1. Copiez le modèle adapté dans un nouveau fichier; gardez les modèles d'origine
   inchangés.
2. Remplissez-le avec les informations du site officiel et donnez au fichier un
   nom clair, par exemple `iit-admission-2026-2027.md`.
3. Gardez les dates, montants et conditions exacts. Si une information manque
   ou si les sources se contredisent, signalez-le et demandez une vérification
   plutôt que de deviner.
4. Faites vérifier le contenu et le lien source par un coéquipier avant de
   l'utiliser.

Ces modèles restent dans `backend/docs/document-templates/`; **ne les placez pas
dans `backend/data/knowledge_base/` et ne les ingérez pas**. Seuls les documents
complétés et vérifiés doivent aller dans la base de connaissances. L'API de
gestion des documents utilise les mêmes catégories, mais n'alimente pas encore
automatiquement l'ingestion RAG.

L'API exige une formation associée (`program_id`). Pour les informations
communes à plusieurs formations, vérifiez avec l'équipe quelle formation
représentera le document; ne dupliquez pas le document sur plusieurs formations
sans que ce soit nécessaire.

## Correspondance API

| Modèle | `doc_type` |
| --- | --- |
| `template-brochure.md` | `brochure` |
| `template-regulation.md` | `regulation` |
| `template-curriculum.md` | `curriculum` |
| `template-admission-conditions.md` | `admission_conditions` |
| `template-equivalence-rules.md` | `equivalence_rules` |
| `template-other.md` | `other` |

Il n'existe pas encore de catégorie `fees` dans l'API. Pour une page de frais,
utilisez `other` et indiquez clairement l'année universitaire et la devise
dans le titre et le contenu.
