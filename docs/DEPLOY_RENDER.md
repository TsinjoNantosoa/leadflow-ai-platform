# Déploiement — backend FastAPI sur Render (Free)

> Préparation uniquement. **Rien n'a été déployé.** `backend/render.yaml` a `autoDeploy: false`.

## Particularités de Render Free

- Le service **s'endort après ~15 min d'inactivité** ; le réveil prend ~30–60 s. **Aucune dépendance à un worker permanent** : l'orchestration est pilotée par n8n (OVH), l'état est en base.
- Conséquences gérées : `GET /health` (sans base) pour le healthcheck ; `GET /api/v1/health` appelé par le frontend à l'ouverture du formulaire pour réveiller le service ; timeouts et reprises côté frontend (`apiFetch`) ; WF-04 réessaie à chaque minute ; l'outbox persiste tout.
- Limite de requête Render ≈ 100 s : l'endpoint `extract` reste borné (< ~80 s, voir `docs/OPENAI_INTEGRATION.md`).

## 1. Créer le service

Render → *New → Blueprint* (ou *Web Service*) depuis le dépôt contenant `backend/` :

- Runtime **Docker**, `dockerfilePath: ./Dockerfile`, `rootDir: backend` si monorepo.
- Port : Render fournit `PORT` ; `scripts/entrypoint.sh` l'utilise (`uvicorn --port ${PORT:-8000}`).
- Healthcheck : `/health`.

## 2. Variables d'environnement

| Variable | Valeur | Remarque |
| --- | --- | --- |
| `APP_ENV` | `production` | Active les contrôles de secrets, `Secure` sur le cookie, désactive `/docs` |
| `DATABASE_URL` | URL Neon **pooled** | `…-pooler…?sslmode=require` |
| `DATABASE_URL_DIRECT` | URL Neon directe | Migrations |
| `RUN_MIGRATIONS_ON_START` | `true` | `alembic upgrade head` au démarrage (idempotent) |
| `FRONTEND_URL` | `https://<projet>.vercel.app` | Contrôle `Origin` + CORS |
| `CORS_ALLOWED_ORIGINS` | *(vide ou aperçus Vercel)* | Origines supplémentaires |
| `SESSION_SECRET` | généré par Render (`generateValue`) | ≥ 32 caractères |
| `API_SERVICE_TOKEN` | généré par Render | **À recopier** dans le credential n8n |
| `SESSION_COOKIE_SAMESITE` | `lax` | Proxy Vercel (même origine) |
| `TRUST_PROXY_HEADERS` | `true` | IP cliente pour le rate limit |
| `DEMO_ADMIN_PASSWORD`, `DEMO_SALES_PASSWORD` | à définir | Pour le seed |
| `LLM_PROVIDER` | `mock` (puis `openai`) | |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | vide/`gpt-4.1-mini` | Requis si `openai` |
| `LLM_DAILY_CALL_LIMIT` | `200` | Garde-fou de coût |
| `CRM_PROVIDER` | `mock` (puis `hubspot`) | Le token HubSpot reste dans n8n |
| `ENABLE_REAL_EMAIL_SEND` | `false` | Toute autre valeur est refusée |

Liste complète et commentée : `backend/.env.example` (une seule source ; aucune variable redondante).

## 3. Premier démarrage

1. Déployez (manuel). Logs : `[entrypoint] alembic upgrade head` puis `Uvicorn running`.
2. `curl https://<service>.onrender.com/health` → `{"status":"ok"}` ; `/health/ready` → `ready`.
3. Seed : *Shell* Render (ou depuis votre poste avec l'URL directe Neon) :
   ```bash
   python -m scripts.seed_demo --users-only      # ou sans option pour les données de démo
   ```
4. Récupérez `API_SERVICE_TOKEN` (Environment) pour n8n.

## 4. Coûts et exploitation

- `LLM_DAILY_CALL_LIMIT` + `llm_usage` bornent la consommation OpenAI (voir dashboard › Vue d'ensemble).
- Logs JSON avec `correlation_id` (Render → Logs). Pas de corps de requête ni de PII.
- Rotation du secret de service : modifier `API_SERVICE_TOKEN` (Render) **et** le credential n8n.

## 5. Rollback

*Deploys → Rollback* sur le dernier déploiement sain. Les migrations Alembic sont **additives** ; pour revenir en arrière sur le schéma : `alembic downgrade -1` depuis votre poste (URL directe) **après sauvegarde** (`docs/DEPLOY_NEON.md`).
