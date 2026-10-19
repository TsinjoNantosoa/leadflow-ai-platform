# LeadFlow AI — Blueprint technique V1

**Intelligent Lead Qualification & Sales Automation Platform**

Ce dossier est un kit de conception, **pas une application déjà développée**. Toutes les données d'exemple sont fictives. Aucun workflow n'est encore connecté à des services externes.

## Contenu

- `CAHIER_DES_CHARGES.md` — cadrage produit, exigences, architecture, plan MVP/V2, métriques.
- `SCHEMA_POSTGRES.sql` — modèle relationnel de référence pour PostgreSQL.
- `WORKFLOWS_N8N.md` — workflows, noeuds, événements et gestion des échecs.
- `API_CONTRATS.md` — routes, payloads, statuts, authentification et idempotence.
- `TESTS_ACCEPTATION.md` — cas de tests et critères de validation.
- `CODEX_SPRINT_01.md` — premier prompt prêt à utiliser pour créer le squelette du projet.
- `.env.example` — liste de variables sans valeur sensible.
- `sample_lead.json` — demande commerciale fictive.

## Architecture proposée

Formulaire React -> FastAPI -> PostgreSQL + outbox -> n8n -> LLM -> FastAPI (qualification + scoring) -> HubSpot (projection CRM) -> brouillon -> validation dans React.

FastAPI contrôle les écritures métier. n8n orchestre des tâches idempotentes. Aucun secret n'est exposé dans le navigateur.

## Première étape

Lire `CAHIER_DES_CHARGES.md`, puis exécuter le prompt `CODEX_SPRINT_01.md` dans un **nouveau dépôt**. Ne connecter aucun compte CRM ou e-mail réel avant que les tests locaux et la validation humaine fonctionnent.
