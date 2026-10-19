# LeadFlow AI — API contracts initiaux

API versionnée, JSON, validation Pydantic ; UUIDs de ressources et `correlation_id` dans les logs.

## Public

### `POST /api/v1/public/leads`

Headers : `Content-Type: application/json`, `Idempotency-Key: <UUID>`.

Body :

```json
{
  "full_name": "Alice Martin",
  "email": "alice@example.org",
  "company": "NovaDigital Demo",
  "requested_service": "automation",
  "message": "Nous souhaitons automatiser notre support; budget indicatif 3000 EUR; démarrage sous un mois.",
  "consent_status": "granted"
}
```

`201 Created` :

```json
{"lead_id":"00000000-0000-4000-8000-000000000001","status":"NEW","request_id":"00000000-0000-4000-8000-000000000002"}
```

Si la même idempotency key est rejouée **avec le même payload**, retourner le même `lead_id` et sans nouvelle création. Même clé + payload différent : `409 Conflict` (pour cela conserver une empreinte de requête en base lors de l'implémentation). Valider le consentement sans forcer un opt-in marketing pour pouvoir demander des informations commerciales.

Erreurs : `400` syntaxe, `422` validation, `429` rate limit, `503` disponibilité.

## Dashboard authentifié

- `GET /api/v1/leads?status=&segment=&page=` : résultats paginés, organisation autorisée.
- `GET /api/v1/leads/{lead_id}` : détails du prospect, qualifications, CRM et brouillons.
- `GET /api/v1/metrics/overview` : stats agrégées réellement calculées.
- `GET /api/v1/automation-runs?lead_id=` : historique sans secrets.
- `PATCH /api/v1/followups/{id}` : modifier un brouillon (commercial autorisé).
- `POST /api/v1/followups/{id}/approve` : validation explicite, **sans envoi**.
- `POST /api/v1/followups/{id}/reject` : rejet, raison facultative.
- `POST /api/v1/leads/{id}/retry` : relancer après contrôle des droits.

La V2 pourra ajouter une route d'envoi séparée sous permissions explicites.

## Endpoints privés (service-to-service uniquement)

- `GET /api/v1/internal/leads/{id}/payload` : infos strictement nécessaires au traitement.
- `POST /api/v1/internal/leads/{id}/qualification` : sortie extraite, scoring serveur, statut et audit.
- `POST /api/v1/internal/leads/{id}/crm-sync` : id externe + statut.
- `POST /api/v1/internal/leads/{id}/followups` : création du brouillon idempotente.
- `POST /api/v1/internal/runs/{id}/status` : durée, état, erreur.

Contrôles : credential machine stocké en secret, TLS, rate limit, permissions par endpoint ; idempotency key sur toute mutation. Aucun `/internal` accessible à un visiteur anonyme.

## Règles de statuts

Lead : `NEW -> PROCESSING -> QUALIFIED -> READY`; bifurcations `MANUAL_REVIEW` ou `FAILED`, puis `ARCHIVED`.

CRM : `PENDING -> SYNCED` ou `RETRYING/FAILED`.

Brouillon : `DRAFT -> APPROVED` ou `REJECTED` ; V2 : `APPROVED -> READY_TO_SEND -> SENT`.

Transitions invalides : `409 Conflict`, avec journal d'audit.
