# API LeadFlow AI (v1)

Source de vérité : **OpenAPI** (`GET /openapi.json`, Swagger UI sur `/docs`, désactivés quand `APP_ENV=production`). Ce document résume les contrats.

Format d'erreur unique : `{"error": {"code": "...", "message": "...", "details": {}}}`. Les valeurs saisies par l'utilisateur ne sont **jamais** renvoyées dans les erreurs de validation (`422`). Chaque réponse porte `X-Correlation-ID` (accepté en entrée s'il est un UUID).

## Public

### `POST /api/v1/public/leads`

En-têtes : `Content-Type: application/json`, **`Idempotency-Key: <UUID>`** (obligatoire).

```json
{
  "full_name": "Alice Martin",
  "email": "alice.martin@example.org",
  "company": "NovaDigital Demo",
  "phone": null,
  "requested_service": "customer_support_automation",
  "message": "Bonjour, notre équipe veut automatiser… Budget indicatif 3000 EUR…",
  "consent_privacy": true,
  "consent_marketing": false
}
```

| Statut | Signification |
| --- | --- |
| `201` | Créé : `{"lead_id", "status": "NEW", "request_id"}` |
| `200` | Rejeu de la même clé **avec le même contenu** : réponse identique, en-tête `Idempotent-Replayed: true`, aucune création |
| `400` | `Idempotency-Key` absente ou invalide |
| `409` | Même clé, contenu différent (journalisé dans l'audit) |
| `422` | Validation (champs inconnus refusés, message 20–4000 caractères, > 3 liens refusés, consentement requis…) |
| `429` | Plafond par IP (hachée) et par heure (`PUBLIC_RATE_LIMIT_PER_HOUR`), `Retry-After` |
| `503` | Base indisponible (réveil Neon) |

`requested_service` ∈ `web_development`, `workflow_automation`, `customer_support_automation`, `ai_integration`, `data_dashboard`, `other`. Un champ `website` rempli (honeypot) renvoie un faux succès sans rien enregistrer.

### `GET /health` · `GET /api/v1/health` · `GET /health/ready`

Liveness (sans base — sûr pendant un cold start) et readiness (vérifie PostgreSQL). `/api/v1/health` passe par le proxy `/api` et sert à réveiller Render.

## Authentification (dashboard)

| Endpoint | Rôle |
| --- | --- |
| `POST /api/v1/auth/login` | `{email, password}` → cookie `lf_session` (HttpOnly) + `{user, csrf_token}` |
| `GET /api/v1/auth/me` | Session courante et jeton CSRF |
| `POST /api/v1/auth/logout` | Révoque la session (`204`) |

Les mutations exigent `X-CSRF-Token`; si `Origin`/`Referer` est présent, il doit appartenir à `FRONTEND_URL`/`CORS_ALLOWED_ORIGINS`.

## Dashboard (session requise ; rôles `ADMIN` ou `SALES`)

| Méthode & chemin | Description |
| --- | --- |
| `GET /api/v1/leads?status=&segment=&service=&q=&review=&page=&page_size=&sort=&order=` | Liste paginée filtrable (`sort` : `created_at`, `score`, `status`, `name`) |
| `GET /api/v1/leads/{id}` | Détail : contact, demande, qualification (+ historique), CRM, brouillons, runs, audit, **timeline** dérivée des enregistrements |
| `POST /api/v1/leads/{id}/retry` | Replanifie un traitement (`202`) ; `409` si déjà en file/en cours ou archivé |
| `GET /api/v1/metrics/overview?days=14` | KPI calculés en SQL (aucune valeur inventée ; `data_origin` distingue démo/réel) |
| `GET /api/v1/automation-runs?lead_id=&status=&workflow=&page=` | Historique des exécutions (jointure outbox : tentatives, prochaine tentative) |
| `POST /api/v1/automation-runs/{id}/retry` | **ADMIN** : reprise manuelle d'un événement `DEAD_LETTER`/`RETRYING` |
| `GET /api/v1/followups?status=` | Brouillons (les `DRAFT` d'abord) |
| `GET /api/v1/followups/{id}/history` | Décisions et modifications |
| `PATCH /api/v1/followups/{id}` | `{subject?, body?, expected_version?}` ; `409 edit_conflict` si la version a changé |
| `POST /api/v1/followups/{id}/approve` | `DRAFT → APPROVED`. **N'envoie aucun e-mail** (idempotent) |
| `POST /api/v1/followups/{id}/reject` | `{reason?}` |

Statuts du lead : `NEW → PROCESSING → QUALIFIED → READY`, bifurcations `MANUAL_REVIEW` / `FAILED`, puis `ARCHIVED`. Brouillon : `DRAFT → APPROVED | REJECTED` (`READY_TO_SEND`/`SENT` sont **impossibles** : contrainte SQL). Une transition invalide renvoie `409` et est auditée.

## Interne — n8n → FastAPI (jamais depuis un navigateur)

Authentification sur **tous** les endpoints : `Authorization: Bearer <API_SERVICE_TOKEN>` + `X-LF-Timestamp: <epoch ms>` (±`INTERNAL_MAX_CLOCK_SKEW_SECONDS`). Mutations : `Idempotency-Key` obligatoire. Sans `API_SERVICE_TOKEN` configuré, l'API interne répond `503` (fail-closed).

| Endpoint | Description |
| --- | --- |
| `POST /internal/outbox/claim` `{limit, worker}` | Réserve des événements prêts ou à lease expirée ; crée un run par tentative. Retourne `event_id`, `event_type`, `lead_id`, `correlation_id`, `attempt`, `run_id`… (aucune donnée personnelle) |
| `POST /internal/outbox/{id}/complete` `{attempt, outcome}` | `SUCCEEDED` ou `MANUAL_REVIEW` ; tentative périmée / déjà livré ⇒ `applied: false` |
| `POST /internal/outbox/{id}/fail` `{attempt, error_code, retryable, message?, retry_after_seconds?}` | `retrying` (backoff) ou `dead_letter` — décision du **backend** |
| `POST /internal/runs/{id}/status` `{step, note?}` | Journalise une étape (run `STARTED` uniquement) |
| `GET /internal/leads/{id}/payload?event_id=` | Données minimales + `already_qualified_for_event` (le texte du prospect n'est pas transmis) |
| `POST /internal/leads/{id}/extract` `{event_id}` | Extraction LLM : `200 {ok:true, extraction…}`, `200 {ok:false, error_code}` (refus/JSON invalide → revue manuelle), `503` (panne, `retryable:true`), `502` (configuration, `retryable:false`) |
| `POST /internal/leads/{id}/qualification` | Score **recalculé** côté serveur, extraction re-validée (budget/citations vérifiés contre le message) |
| `POST /internal/leads/{id}/manual-review` | Bascule en `MANUAL_REVIEW` |
| `GET /internal/leads/{id}/crm-context` | Contact, mapping, **`CRM_PROVIDER`** |
| `POST /internal/leads/{id}/crm/mock-upsert` | CRM factice (idempotent) |
| `POST /internal/leads/{id}/crm-sync` | Enregistre `SYNCED`/`RETRYING`/`FAILED` ; `409` si l'identifiant externe diffère de celui déjà lié |
| `GET /internal/leads/{id}/draft-context` · `POST …/draft/generate` · `POST …/followups` | Rédaction (politique de contenu appliquée deux fois) et création idempotente d'un brouillon `DRAFT` |

Rejeu : même `Idempotency-Key` + même corps ⇒ même réponse (`Idempotent-Replayed: true`) ; corps différent ⇒ `409 idempotency_key_reuse`.
