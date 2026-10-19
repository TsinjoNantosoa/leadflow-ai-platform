# LeadFlow AI — Intelligent Lead Qualification & Sales Automation

Plateforme de qualification de demandes commerciales pour agences et PME B2B : formulaire → validation → **PostgreSQL + outbox** → orchestration **n8n** → extraction **OpenAI** (sorties structurées) → **score explicable déterministe** → **CRM (HubSpot ou mock)** → **brouillon de réponse relu par un humain**. Scénario de démonstration : l'agence **fictive** NovaDigital.

> **Aucun e-mail commercial n'est jamais envoyé** : le code ne contient aucune fonction d'envoi et la base interdit les statuts `SENT`/`READY_TO_SEND`. Toutes les données fournies sont synthétiques (`@example.org`).

## Fonctionnalités

- Formulaire public : validation stricte, consentements, anti-spam (honeypot, plafond par IP hachée), **idempotence** (`Idempotency-Key`), déduplication des contacts (e-mail normalisé), un contact → plusieurs leads.
- Pipeline fiable : **outbox transactionnelle**, réservation atomique avec lease, reprise après crash, backoff + dead-letter décidés par le backend, `correlation_id` partout.
- IA : extraction (intention, service, budget, échéance, langue, citations) sous schéma strict, **défense contre l'injection de prompt**, revue humaine automatique en cas de doute ; brouillons soumis à une politique (aucun prix/délai/engagement inventé).
- Score `scoring-v1` (0–100, HOT ≥ 75 / WARM ≥ 45) **calculé par le serveur**, facteurs et données utilisées conservés.
- Dashboard (8 pages) : indicateurs réels depuis PostgreSQL, liste filtrable, fiche lead avec **timeline** du parcours, revue humaine (modifier / approuver / rejeter + historique), monitor des automatisations (reprise manuelle admin).
- Sécurité : sessions serveur (cookie HttpOnly), CSRF, rôles `ADMIN`/`SALES`, endpoints internes par jeton de service + anti-rejeu.

## Architecture

```
Frontend (Vercel) ──/api (même origine)──► FastAPI (Render) ◄──► PostgreSQL (Neon)
                                               ▲   │ Structured Outputs
        n8n (VPS OVH existant) ── HTTPS ───────┘   └──► OpenAI
        LF-WF-04 (planifié) → LF-WF-01 qualif · LF-WF-02 CRM · LF-WF-03 brouillon
```
Détails, décisions et corrections du blueprint : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Arborescence

| Dossier | Contenu |
| --- | --- |
| [`frontend/`](frontend/README.md) | React 19 + TypeScript + Vite + Tailwind 4 — déployable seul (Vercel) |
| [`backend/`](backend/README.md) | FastAPI + SQLAlchemy 2 + Alembic + OpenAI — déployable seul (Render, Docker) |
| [`automation/n8n/`](automation/n8n/README.md) | 4 workflows JSON importables + [guide d'import](automation/n8n/IMPORT_GUIDE.md) |
| [`docs/`](docs/) | Architecture, API, OpenAI, base, sécurité, déploiements, rapport de tests, checklist |
| `docs/blueprint/` | Blueprint d'origine (conservé tel quel) |
| `docker-compose.yml` | PostgreSQL local (+ n8n **jetable** en profil optionnel) |

## Prérequis

Python 3.12 · Node ≥ 20.19 · Docker (PostgreSQL local) · (optionnel) une clé OpenAI, un compte HubSpot de test.

## Démarrage rapide (100 % local, sans clé externe)

```bash
docker compose up -d db                                   # PostgreSQL sur localhost:5433

# Backend
cd backend && python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt         # Linux/macOS : .venv/bin/pip
cp .env.example .env                                      # définir API_SERVICE_TOKEN (ex. une chaîne aléatoire de 40+ caractères)
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m scripts.seed_demo                 # note les mots de passe affichés (ou DEMO_*_PASSWORD)
.venv/Scripts/python -m uvicorn app.main:app --port 8000

# Traitement des événements sans n8n (autre terminal)
.venv/Scripts/python -m scripts.dev_worker --base-url http://localhost:8000 --token "<API_SERVICE_TOKEN>" --loop

# Frontend (autre terminal)
cd frontend && npm ci && npm run dev                      # http://localhost:5173
```
Ouvrez `/demo`, soumettez le scénario préremplissable, connectez-vous (`sales@novadigital.example`), suivez le parcours du lead, relisez et approuvez le brouillon. `LLM_PROVIDER=mock` et `CRM_PROVIDER=mock` sont les valeurs par défaut.

## Tests

| Suite | Commande | Voir |
| --- | --- | --- |
| Backend (pytest, PostgreSQL réel) | `cd backend && .venv/Scripts/python -m pytest` | [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) |
| Frontend (types, lint, unitaires, build) | `cd frontend && npm run typecheck && npm run lint && npm test && npm run build` | idem |
| End-to-end (Playwright) | `cd frontend && npx playwright test` | idem |
| Workflows n8n sur n8n local + faux HubSpot | voir `automation/n8n/README.md` | idem |

## Déploiement (préparé, **non exécuté**)

[Vercel](docs/DEPLOY_VERCEL.md) · [Render](docs/DEPLOY_RENDER.md) · [Neon](docs/DEPLOY_NEON.md) · [n8n sur OVH](docs/DEPLOY_N8N_OVH.md) · [Checklist avant activation d'une intégration réelle](docs/RELEASE_CHECKLIST.md).

## Honnêteté sur ce qui est validé

Voir le rapport final et [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md). En bref : l'intégration OpenAI et HubSpot **réelles** n'ont **pas** été exécutées (aucune clé) ; le code OpenAI est testé contre le SDK officiel avec un transport simulé ; la branche HubSpot a été exécutée sur un **vrai n8n local** contre un **faux** serveur HubSpot ; rien n'a été déployé.
