# Base de données

PostgreSQL 15+ (testé 16 en local ; Neon). Toute évolution passe par **Alembic** (`backend/alembic/versions/`). Le fichier `docs/blueprint/SCHEMA_POSTGRES.sql` d'origine n'a servi que de point de départ (il n'avait jamais été exécuté).

## Tables

| Table | Rôle | Points clés |
| --- | --- | --- |
| `organizations` | Tenant (mono-tenant au MVP) | `slug` unique |
| `users`, `sessions` | Auth | rôle `ADMIN`/`SALES` (CHECK) ; session : **hash HMAC** du jeton, jeton CSRF, expiration, révocation ; verrouillage après échecs |
| `contacts` | Un contact par e-mail normalisé | `UNIQUE(organization_id, email_normalized)` ; `CHECK email_normalized = lower(btrim(...))` ; `UNIQUE(organization_id, id)` (cible de FK composite) |
| `leads` | Une **demande** ; plusieurs par contact | FK composite `(organization_id, contact_id) → contacts` ; statut CHECK ; `is_demo` ; version de la notice et date du consentement |
| `intake_events` | Idempotence publique | `UNIQUE(organization_id, client_request_id)`, empreinte du corps, **IP hachée** (HMAC) pour le rate limit |
| `qualifications` | Versionnées par lead | score 0–100 et segment cohérents (CHECK), `score_explanation` JSONB, `extracted_data`, `source_event_id` unique (idempotence), `prompt_version`, `scoring_rule_version` |
| `crm_mappings` | Projection CRM | unicité `(org, contact, provider)` et `(org, provider, external_id)` ; états `PENDING/SYNCED/RETRYING/FAILED` |
| `mock_crm_contacts` | CRM factice (`CRM_PROVIDER=mock`) | upsert idempotent |
| `followups` | Brouillons | `CHECK status NOT IN ('READY_TO_SEND','SENT') AND sent_at IS NULL` — **l'envoi est impossible au niveau SQL** ; `edit_version` (concurrence optimiste) ; `creation_event_id` unique |
| `outbox_events` | Outbox transactionnelle | `dedupe_key` unique, `status`, `attempt_count`/`max_attempts`, `next_attempt_at`, `locked_until`/`locked_by` (lease), `correlation_id` |
| `automation_runs` | Une exécution = une tentative | `UNIQUE(outbox_event_id, attempt_count)` |
| `audit_events` | Journal | acteur (`system`/`user`/`service`), action, métadonnées, corrélation |
| `idempotency_records` | Rejeu sûr des mutations internes | `UNIQUE(scope, key)` + empreinte |
| `llm_usage` | Traçabilité des appels LLM | tokens, latence, statut, coût estimé (si tarifs configurés) |

Index principaux : `(org, created_at)` et `(org, status)` sur `leads`, `(status, next_attempt_at)` et `(status, locked_until)` sur l'outbox, `(correlation_id)` sur les runs, `(client_ip_hash, created_at)` sur l'intake.

## Concurrence et intégrité

- Contact : `INSERT … ON CONFLICT (org, email_normalized) DO UPDATE` ⇒ un seul contact même en soumissions simultanées (test avec 8 threads).
- Idempotence : `pg_advisory_xact_lock` sur la clé ⇒ les doublons concurrents sont sérialisés et voient le résultat du premier.
- Outbox : `SELECT … FOR UPDATE SKIP LOCKED` ⇒ deux workers ne réservent jamais le même événement ; lease expirée ⇒ reprise ; tentative périmée ⇒ ignorée.
- Brouillons : verrou de ligne + `edit_version` ⇒ approbation/rejet simultanés : une seule décision l'emporte.

## Données de démonstration

`python -m scripts.seed_demo` : organisation, 2 comptes (mots de passe via `DEMO_*_PASSWORD`, sinon **générés et affichés une fois** ; obligatoires en production), 15 leads synthétiques (`@example.org`, `is_demo = true`) : HOT/WARM/COLD, demande incomplète, FR/EN/ES, revue manuelle (injection, extraction invalide), CRM `RETRYING`/`FAILED`, brouillons `DRAFT`/`APPROVED`/`REJECTED`, automatisation en dead-letter. Réexécutable (identifiants `uuid5` déterministes), **n'écrase rien**, et les événements de démo non terminaux sont inertes (jamais réservés par un vrai n8n). `--users-only` pour la production.

## Scripts d'exploitation (`backend/scripts/`)

| Script | Usage |
| --- | --- |
| `verify_schema.py` | Révision = head, aucune dérive modèles/base, garde-fous SQL présents (code de sortie ≠ 0 sinon) |
| `purge_retention.py [--apply]` | Rétention : outbox livrée > `RETENTION_OUTBOX_DAYS`, idempotence, sessions. Simulation par défaut ; ne touche jamais leads/contacts/dead-letters |
| `contact_data.py export|delete --email … [--apply]` | Export / effacement des données d'un contact (le CRM externe est à traiter séparément) |
| `e2e_prepare.py` | Base jetable `*_playwright` pour les tests E2E |

## Neon (production de démonstration)

Voir `docs/DEPLOY_NEON.md` (URL *pooled* vs directe, SSL, pooling, sauvegardes/restauration).
