# Déploiement — backend FastAPI sur Render (Free)

> Préparation uniquement. **Rien n'a été déployé.** `backend/render.yaml` a `autoDeploy: false`.

## Particularités de Render Free

- Le service **s'endort après ~15 min d'inactivité** ; le réveil prend ~30–60 s. **Aucune dépendance à un worker permanent** : l'orchestration est pilotée par n8n (OVH), l'état est en base.
- Conséquences gérées : `GET /health` (sans base) pour le healthcheck ; `GET /api/v1/health` appelé par le frontend à l'ouverture du formulaire pour réveiller le service ; timeouts et reprises côté frontend (`apiFetch`) ; WF-04 reprend toutes les ~20 min (réglable) et est réveillé immédiatement par le backend après chaque soumission (best-effort) ; l'outbox persiste tout.
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
| `TRUST_PROXY_HEADERS` | `true` | IP cliente pour le rate limit (lue depuis la **droite** de `X-Forwarded-For`) |
| `TRUSTED_PROXY_HOPS` | `1` | Nombre de proxys de confiance devant l'API (Render seul = 1). Vérifier en production avec un appel de test ; en cas de doute, laisser `TRUST_PROXY_HEADERS=false` (le rate limit voit alors l'IP du proxy) |
| `N8N_WAKE_WEBHOOK_URL` | *(vide)* ou `https://<n8n>/webhook/lf-wf-04-wake` | Réveil best-effort de WF-04 après une soumission |
| `N8N_WEBHOOK_SECRET` | *(vide)* ou secret partagé | Même valeur que le credential n8n `LF - n8n Webhook Secret` |
| `DEMO_ADMIN_PASSWORD`, `DEMO_SALES_PASSWORD` | *(laisser vide en production)* | Uniquement pour le seed de démonstration, exécuté depuis votre poste |
| `LLM_PROVIDER` | `mock` (puis `openai`) | |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | vide/`gpt-4.1-mini` | Requis si `openai` |
| `LLM_DAILY_CALL_LIMIT` | `200` | Garde-fou de coût |
| `CRM_PROVIDER` | `mock` (puis `hubspot`) | Le token HubSpot reste dans n8n |
| `ENABLE_REAL_EMAIL_SEND` | `false` | Toute autre valeur est refusée |

Liste complète et commentée : `backend/.env.example` (une seule source ; aucune variable redondante).

## 3. Initialisation de la base — **sans Shell Render**

L'offre Free ne donne pas de Shell/SSH. Toute l'initialisation se fait **depuis votre poste (environnement de confiance)**, contre Neon, avec l'URL **directe** (non poolée) et `sslmode=require`. Il n'existe volontairement **aucun endpoint HTTP** de migration ou de seed.

```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Linux/macOS : .venv/bin/...
export DATABASE_URL="postgresql+psycopg://<user>:<pwd>@<hote-direct>.neon.tech/<db>?sslmode=require"   # PowerShell : $env:DATABASE_URL=...
export DATABASE_URL_DIRECT="$DATABASE_URL"
python -m alembic upgrade head          # idempotent : sans effet si déjà à jour
python -m scripts.verify_schema         # contrôle modèles = base (lecture seule)
```

Premier administrateur (idempotent, aucune donnée de démonstration) :

```bash
LF_ADMIN_EMAIL=vous@votre-domaine.tld python -m scripts.create_admin     # mot de passe demandé sans écho (≥ 12 caractères)
```
Si l'utilisateur existe, rien n'est modifié ; `--reset-password` le change explicitement. Données de démonstration (optionnel, marquées `is_demo`) : `python -m scripts.seed_demo` — **à éviter sur une base contenant de vraies données** ; les comptes démo (`*@novadigital.example`) ne doivent pas rester actifs si le service est public.

`RUN_MIGRATIONS_ON_START=true` reste possible : le démarrage exécute `alembic upgrade head` (idempotent, additif). Si vous préférez maîtriser le moment des migrations, laissez `false` et lancez-les d'abord depuis votre poste.

**Récupération en cas d'erreur** : migration interrompue → Alembic est transactionnel (DDL PostgreSQL) : corrigez et relancez la même commande ; mauvaise migration appliquée → sauvegarde `pg_dump` préalable (`docs/DEPLOY_NEON.md`) puis `alembic downgrade -1` ; service qui ne démarre pas → *Rollback* Render (la base reste compatible, migrations additives).

## 3 bis. Premier démarrage

1. Déployez (manuel). Logs : `Uvicorn running` (et `[entrypoint] alembic upgrade head` si activé).
2. `curl https://<service>.onrender.com/health` → `{"status":"ok"}` ; `/health/ready` → `{"status":"ready"}` (interroge Neon ; au **réveil de Neon** — suspension après inactivité — la première requête peut échouer puis réussir : le pool détecte les connexions mortes, `pool_pre_ping`).
3. Récupérez `API_SERVICE_TOKEN` (Environment) pour le credential n8n.

## 4. Coûts et exploitation

- `LLM_DAILY_CALL_LIMIT` + `llm_usage` bornent la consommation OpenAI (voir dashboard › Vue d'ensemble).
- Logs JSON avec `correlation_id` (Render → Logs). Pas de corps de requête ni de PII.
- Rotation du secret de service : modifier `API_SERVICE_TOKEN` (Render) **et** le credential n8n.

## 5. Rollback

*Deploys → Rollback* sur le dernier déploiement sain. Les migrations Alembic sont **additives** ; pour revenir en arrière sur le schéma : `alembic downgrade -1` depuis votre poste (URL directe) **après sauvegarde** (`docs/DEPLOY_NEON.md`).

## 6. Heures Render Free et fréquence de polling

Render Free dort après ~15 min sans trafic. Un appel de WF-04 toutes les **5 min** garderait le service **éveillé en permanence** (donc consommerait les heures gratuites) ; ce n'est pas une optimisation. Avec le réveil best-effort après soumission, WF-04 n'a plus besoin de sonder fréquemment : le poll de récupération par défaut est de **20 min** (réglable, voir `automation/n8n/README.md`). Compromis : retard maximal de reprise d'un événement manqué ≈ intervalle du poll ; chaque poll peut réveiller Render (cold start ~30–60 s, sans conséquence car n8n attend jusqu'à 90 s) ; ~72 exécutions n8n/jour à 20 min.
