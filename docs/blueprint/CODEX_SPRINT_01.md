# Prompt Codex — LeadFlow AI Sprint 1

Tu es Senior Full-Stack Engineer et architecte orienté fiabilité. Tu vas construire le **squelette fonctionnel MVP LeadFlow AI** dans un nouveau dépôt, à partir du dossier de conception fourni.

1. LIS d'abord l'intégralité des fichiers `CAHIER_DES_CHARGES.md`, `SCHEMA_POSTGRES.sql`, `API_CONTRATS.md`, `WORKFLOWS_N8N.md`, `TESTS_ACCEPTATION.md`.
2. Si un dépôt existe, audite son contenu et protège les modifications locales ; ne lance aucun `git reset --hard`.
3. Propose un plan bref des fichiers et commandes, puis implémente Sprint 1 sans déployer.
4. Stack : Python FastAPI + Pydantic + SQLAlchemy + Alembic ; React + TypeScript + Vite ; PostgreSQL en Docker Compose. Réutilise la stack existante si elle diffère et est déjà opérationnelle.
5. Structure suggérée : `apps/api`, `apps/web`, `db/migrations`, `automation/n8n`, `tests`, `docs`, `docker-compose.yml`.
6. Crée le schéma PostgreSQL via Alembic. Sépare `contacts` et `leads` (même contact, plusieurs demandes). Préserve un `organization_id` unique par MVP et prépare de futures règles multi-tenant.
7. Développe le formulaire public, `POST /api/v1/public/leads` avec validation, limites d'entrée, normalisation d'e-mail, idempotency-key, sauvegarde contact/lead et événement outbox dans la même transaction.
8. Implémente `LLM_PROVIDER=mock`, `CRM_PROVIDER=mock` par défaut, sans aucun appel API réel ni e-mail automatique. Toute connexion réelle reste inactive pour ce premier sprint.
9. Crée un endpoint `/health` et une page dashboard minimale en mode données fictives stockées en base, protégée par une authentification de démonstration correcte côté serveur (pas un secret statique dans React). Ne prétends pas avoir construit le RBAC V2.
10. Ajoute des tests ciblant validation, doublons, idempotence, séparation contact/lead, création outbox, accès dashboard non authentifié et comportement mock.
11. Génère `.env.example` sans secrets et `README.md` avec commandes de lancement et d'exécution des tests.
12. Exécute build, lint, typecheck et tests disponibles. Répare les erreurs que tu introduis. Inspecte le diff final.

**Ne lance pas Git push, Render, Neon, HubSpot ou n8n de production. Ne publie ni clés ni données personnelles.**

À la fin, rends un compte rendu : fichiers créés, endpoints fonctionnels, captures si possible, tests exécutés et résultats, limites non couvertes, prochain sprint précis pour intégration n8n + IA.
