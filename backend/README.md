# LeadFlow AI — backend (FastAPI)

API **FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + PostgreSQL**, intégration **OpenAI** (SDK officiel, Structured Outputs) avec mode **mock** complet. Application **autonome** : ne dépend pas du build React, déployable seule sur Render.

```
app/
├── main.py            # application, CORS, middlewares, health
├── core/              # config (pydantic-settings), constantes métier, erreurs
├── database/          # engine/session, base déclarative
├── models/            # SQLAlchemy (core.py, pipeline.py)
├── schemas/           # Pydantic (public, dashboard, extraction LLM)
├── security/          # Argon2, sessions, dépendances d'auth (utilisateur / service)
├── services/          # intake, outbox, scoring, qualification, crm, followups, views, timeline, seed…
├── integrations/      # llm/ (mock, factory) et openai/ (client, schémas, prompts)
├── observability/     # logs JSON + corrélation, en-têtes de sécurité
└── api/v1/            # public, auth, dashboard, internal (n8n)
alembic/               # migrations versionnées (0001_initial_schema)
scripts/               # seed_demo, verify_schema, purge_retention, contact_data, dev_worker, e2e_prepare, entrypoint.sh
tests/                 # pytest (PostgreSQL réel)
```

## Démarrage local

```bash
docker compose up -d db                       # (racine) PostgreSQL 16 sur le port 5433 + base leadflow_test
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt     # Linux/macOS : .venv/bin/pip
cp .env.example .env                          # puis renseigner SESSION_SECRET et API_SERVICE_TOKEN (>= 32 car. conseillé)
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m scripts.seed_demo     # comptes + 15 leads synthétiques ; affiche les mots de passe générés
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```
Swagger : <http://localhost:8000/docs>. Healthchecks : `/health` (sans base), `/health/ready` (base).

Traiter les événements **sans n8n** (remplaçant local, mêmes appels HTTP que les workflows) :
```bash
.venv/Scripts/python -m scripts.dev_worker --base-url http://localhost:8000 --token "$API_SERVICE_TOKEN" --loop
```

## Authentification

Sessions serveur : `POST /api/v1/auth/login` pose un cookie `HttpOnly` ; les mutations exigent `X-CSRF-Token` (renvoyé par `login`/`me`) et un `Origin` autorisé. Rôles `ADMIN`/`SALES`. Comptes créés par `seed_demo` (`admin@novadigital.example`, `sales@novadigital.example`) avec `DEMO_*_PASSWORD` ou un mot de passe généré affiché une fois. Détails : [`docs/SECURITY.md`](../docs/SECURITY.md).

## Tests

```bash
.venv/Scripts/python -m pytest                 # base leadflow_test (jetable, recréée par la session de tests)
.venv/Scripts/python -m ruff check .
```
`TEST_DATABASE_URL` peut surcharger l'URL ; son nom **doit finir par `_test`** (garde-fou : les tests tronquent les tables). Test OpenAI réel (désactivé par défaut) : `docs/OPENAI_INTEGRATION.md`.

## Variables d'environnement

Contrat unique et commenté : [`.env.example`](./.env.example). Points importants : `DATABASE_URL`/`DATABASE_URL_DIRECT` (Neon), `FRONTEND_URL`/`CORS_ALLOWED_ORIGINS`, `SESSION_SECRET`, `API_SERVICE_TOKEN`, `LLM_PROVIDER`/`OPENAI_*`, `CRM_PROVIDER`, `OUTBOX_*`. `ENABLE_REAL_EMAIL_SEND` doit rester `false` (toute autre valeur est refusée).

## Déploiement Render

[`docs/DEPLOY_RENDER.md`](../docs/DEPLOY_RENDER.md) · `Dockerfile` (utilisateur non-root, healthcheck) · `render.yaml` (`autoDeploy: false`) · `scripts/entrypoint.sh` (`RUN_MIGRATIONS_ON_START`).

## Règles métier à retenir

- **Aucun envoi d'e-mail** : le code ne contient aucune fonction d'envoi ; la base interdit `SENT`/`READY_TO_SEND`.
- **Score** déterministe (`scoring-v1`), jamais calculé par le LLM ; budget absent ⇒ `null`, jamais inventé.
- **Outbox** : écrite dans la transaction du lead ; réservation `SKIP LOCKED` + lease ; le backend décide des retries ; dead-letter après `OUTBOX_MAX_ATTEMPTS`.
- **Idempotence** : formulaire public (`Idempotency-Key` + empreinte) et mutations internes (clé + empreinte + verrou consultatif).
