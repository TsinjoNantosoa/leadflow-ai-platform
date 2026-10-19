# Workflows n8n LeadFlow AI

Quatre exports **importables**, livrés **désactivés** (`"active": false`), sans secret, préfixés `LF-` pour ne jamais se confondre avec vos autres projets. Cible : **n8n ≥ 1.100** (validés sur **2.43.8**). Procédure d'import sur votre instance OVH : [`IMPORT_GUIDE.md`](./IMPORT_GUIDE.md).

| Fichier | Nom du workflow | Déclencheur | Rôle |
| --- | --- | --- | --- |
| `WF-04-Operations-Recovery.json` | `LF-WF-04 Operations Recovery` | Schedule (1 min) + Manual + Error Trigger | Réserve les événements outbox (lease), route vers WF-01/02/03, rapporte les échecs de dispatch, alerte |
| `WF-01-Lead-Qualification.json` | `LF-WF-01 Lead Qualification` | Webhook (secret) | `LEAD_SUBMITTED` → extraction (FastAPI→OpenAI) → validation → qualification + score serveur |
| `WF-02-HubSpot-CRM-Sync.json` | `LF-WF-02 HubSpot CRM Sync` | Webhook (secret) | `CRM_SYNC_REQUESTED` → mock ou HubSpot (recherche → màj/création → réconciliation) → résultat enregistré |
| `WF-03-Followup-Draft.json` | `LF-WF-03 Followup Draft` | Webhook (secret) | `DRAFT_REQUESTED` → rédaction → contrôle → brouillon `DRAFT` → **stop** (aucun envoi) |

## Principes

- **Pull, pas push** : Render Free peut dormir. WF-04 est **réveillé par le backend** (webhook `lf-wf-04-wake`, best-effort) après chaque soumission et sonde l'API par **filet de récupération toutes les 20 min** (réglable : `python tools/build_workflows.py --poll-minutes 30`, ou éditer le nœud *Schedule Trigger*). L'état vit dans PostgreSQL ; perdre un réveil ne perd aucun événement.
- **Le backend est l'unique autorité des retries.** Aucun nœud n'a de « Retry on fail » : chaque échec est rapporté (`/outbox/{id}/fail`) et l'API décide (backoff exponentiel + jitter, `max_attempts`, dead-letter). Un 200 du webhook enfant (`202`) n'est **qu'un accusé** ; le succès métier est `complete`.
- **Aucune clé OpenAI dans n8n.** n8n appelle `…/extract` et `…/draft/generate` ; FastAPI parle à OpenAI.
- **Aucun nœud d'envoi d'e-mail** dans aucun workflow (`grep -i "send\|email\|smtp\|gmail"` ne retourne que des commentaires).
- **Idempotence** : chaque appel porte `Idempotency-Key = event_id:attempt:étape` ; rejouer un workflow ne crée ni second brouillon, ni seconde qualification, ni second contact CRM.
- **Anti-rejeu** : `X-LF-Timestamp: {{ Date.now() }}` sur chaque appel interne.
- **Configuration sans variables d'environnement** : n8n ≥ 2 bloque `$env` dans les nœuds par défaut. Chaque workflow commence par un nœud **`LF Config`** (Set) portant les paramètres à éditer ; les secrets sont dans des **credentials**.

## Credentials à créer (types n8n)

| Nom exact (à créer) | Type | Valeur | Utilisé par |
| --- | --- | --- | --- |
| `LF - LeadFlow API Service Token` | Header Auth | Name `Authorization`, Value `Bearer <API_SERVICE_TOKEN>` | WF-01, 02, 03, 04 |
| `LF - n8n Webhook Secret` | Header Auth | Name `X-LeadFlow-Webhook-Secret`, Value = secret aléatoire de votre choix | WF-01/02/03 (Webhook) et WF-04 (appel) |
| `LF - HubSpot Private App Token` | HubSpot App Token | Token d'une Private App (scopes `crm.objects.contacts.read` + `.write`) | WF-02 — **uniquement si `CRM_PROVIDER=hubspot`** |

## Paramètres à éditer après import (nœud « LF Config »)

| Workflow | Champ | Valeur |
| --- | --- | --- |
| WF-01, 02, 03, 04 | `api_base_url` | `https://<votre-service>.onrender.com/api/v1/internal` (sans `/` final) |
| WF-04 | `n8n_base_url` | URL de **cette** instance n8n (ex. `https://n8n.mondomaine.tld`, ou `http://localhost:5678` si WF-04 appelle ses propres webhooks en boucle locale) |
| WF-04 | `claim_limit` | 5 par défaut (max 20 côté API) |

Webhooks exposés : `POST /webhook/lf-wf-01-lead-qualification`, `/webhook/lf-wf-02-crm-sync`, `/webhook/lf-wf-03-followup-draft` (auth Header Auth).

## Variables côté API (pas côté n8n)

`CRM_PROVIDER` (`mock`/`hubspot`), `LLM_PROVIDER`, `OPENAI_*`, `OUTBOX_*` sont des variables **FastAPI** : n8n lit `CRM_PROVIDER` via `GET …/crm-context` et ne duplique aucune règle.

## Niveau de validation (honnête)

| Élément | Niveau |
| --- | --- |
| Structure JSON, connexions, nœuds accessibles, aucun secret | Vérifié par script (`build_workflows.py` valide le câblage) |
| Import dans un n8n **2.43.8** réel (Docker local jetable) | **Exécuté** : les 4 workflows s'importent et se publient |
| Chaîne WF-04 → WF-01 → WF-02 → WF-03 en mode `mock` | **Exécutée sur n8n réel** : lead `READY`, 3 événements livrés |
| Branche HubSpot de WF-02 (création, mise à jour, 409, 429, 401, timeout après succès) | **Exécutée sur n8n réel contre un FAUX serveur HubSpot local** (`tools/fake_hubspot.py`) — voir `docs/TEST_REPORT.md` |
| Appels réels à **HubSpot** (vrai token, vraie API) | **NON exécutés** |
| Import / exécution sur **votre instance OVH** | **NON effectués** (interdit sans votre accord) |
| Versions de n8n < 1.100 | Non testées |

## Régénérer les JSON

```bash
python automation/n8n/tools/build_workflows.py
```
Les JSON sont **générés** par ce script (câblage vérifié, identifiants de nœuds déterministes) ; modifiez le script, pas les JSON.

## Validation locale (n8n jetable + faux HubSpot)

```bash
docker compose --profile n8n up -d n8n          # n8n 2.43.8 sur http://localhost:5679 (instance de TEST)
python automation/n8n/tools/fake_hubspot.py --port 9100
# remplacer les placeholders par les URL de test dans une COPIE des JSON, importer (docker exec … n8n import:workflow),
# publier, puis :
python automation/n8n/tools/run_local_scenarios.py --database-url postgresql+psycopg://…/leadflow_e2e
```
`run_local_scenarios.py` soumet des demandes fictives, attend la stabilisation et vérifie en base et côté faux HubSpot : création, mise à jour sans doublon, 429 puis succès, **timeout après succès sans second contact**, 401 → dead-letter, LLM invalide → revue manuelle, panne LLM → retry planifié.
