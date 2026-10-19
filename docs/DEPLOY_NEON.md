# Déploiement — base PostgreSQL sur Neon

> Ce guide **prépare** l'opération. Rien n'a été créé ni modifié sur Neon par l'assistant : exécutez-le vous-même.

## 1. Créer le projet

Neon → *New project* (région proche de Render, ex. `eu-central-1`), **projet dédié** à LeadFlow (ne partagez pas avec d'autres produits). Notez les **deux chaînes de connexion** :

| Usage | Hôte | Variable |
| --- | --- | --- |
| Application (beaucoup de connexions courtes) | `ep-xxx-pooler.<région>.aws.neon.tech` (**-pooler**) | `DATABASE_URL` |
| Migrations Alembic (DDL, session complète) | `ep-xxx.<région>.aws.neon.tech` (direct) | `DATABASE_URL_DIRECT` |

Les deux se terminent par `?sslmode=require` (**obligatoire**). Un préfixe `postgres://` ou `postgresql://` est converti automatiquement vers le driver `psycopg 3` (`postgresql+psycopg://`).

## 2. Pourquoi deux URL ?

- Le pooler Neon est un **PgBouncer en mode transaction** : le backend désactive les requêtes préparées (`prepare_threshold=None`) et n'utilise que des verrous **de transaction** (`pg_advisory_xact_lock`), compatibles.
- Les migrations utilisent l'URL directe (DDL transactionnel complet) : `alembic/env.py` lit `DATABASE_URL_DIRECT` et retombe sur `DATABASE_URL` si elle est vide.

## 3. Pooling et réveil

- Pool applicatif : `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`, `DB_POOL_RECYCLE_SECONDS=300`, `pool_pre_ping` actif.
- Le calcul Neon Free se met en veille : la première requête après inactivité peut prendre 1–3 s ; `DB_CONNECT_TIMEOUT_SECONDS=15` et le mécanisme de reconnexion le couvrent. Une base injoignable renvoie `503` + `Retry-After` (jamais de 500 trompeur).

## 4. Initialisation prudente

Depuis votre poste (ou via le démarrage du conteneur Render avec `RUN_MIGRATIONS_ON_START=true`) :

```bash
cd backend
export DATABASE_URL_DIRECT='postgresql://USER:PASS@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require'
export DATABASE_URL="$DATABASE_URL_DIRECT"
python -m alembic upgrade head          # idempotent : ne modifie rien si déjà à jour
python -m scripts.verify_schema         # doit afficher « OK »
```

Seed (comptes + démonstration) — **uniquement sur une base de démonstration** :

```bash
export DEMO_ADMIN_PASSWORD='…≥10 caractères…' DEMO_SALES_PASSWORD='…'
python -m scripts.seed_demo             # organisation + comptes + 15 leads synthétiques
python -m scripts.seed_demo --users-only   # production : sans leads de démonstration
```
Le seed est réexécutable et n'écrase rien. En production, il **refuse** de créer des comptes sans mots de passe explicites.

> ⚠️ Ne lancez jamais `pytest` avec `DATABASE_URL`/`TEST_DATABASE_URL` pointant vers Neon : les tests tronquent les tables. Le garde-fou exige un nom de base finissant par `_test`.

## 5. Sauvegardes et restauration

- **Neon (plan Free)** : *Point-in-time restore* limité (fenêtre courte selon le plan, à vérifier dans la console) — pas une sauvegarde durable.
- **Sauvegarde logique recommandée** (hebdomadaire ou avant chaque évolution) :
  ```bash
  pg_dump "$DATABASE_URL_DIRECT" --format=custom --no-owner --file=leadflow-$(date +%F).dump
  ```
- **Restauration** vers une base vide (jamais « par-dessus » la production) :
  ```bash
  createdb … leadflow_restore   # ou nouvelle branche Neon
  pg_restore --no-owner --dbname="postgresql://…/leadflow_restore?sslmode=require" leadflow-2026-10-19.dump
  python -m scripts.verify_schema   # avec DATABASE_URL pointant sur la base restaurée
  ```
- **Branches Neon** : créez une branche avant une migration risquée ; supprimez-la après validation.

## 6. Rétention

Planifiez `python -m scripts.purge_retention --apply` (par exemple via un workflow n8n *Execute Command* ou un cron externe) ; commencez par la simulation (sans `--apply`).

## 7. Contrôles après mise en service

`GET https://<api>/health/ready` → `{"status":"ready"}` · dashboard → *Vue d'ensemble* sans erreur · `verify_schema` → OK.
