# Checklist de mise en service

Cochez dans l'ordre. Rien de cette liste n'a été exécuté sur vos services distants.

## A. Avant tout déploiement

- [ ] Relire `docs/TEST_REPORT.md` : suites exécutées, résultats, limites.
- [ ] `git status` : aucun fichier `.env`, aucune clé, aucun dump dans l'index (`.gitignore` les exclut).
- [ ] Générer **deux secrets distincts** (≥ 48 caractères) : `SESSION_SECRET`, `API_SERVICE_TOKEN` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).
- [ ] Choisir les mots de passe démo (`DEMO_ADMIN_PASSWORD`, `DEMO_SALES_PASSWORD`, ≥ 10 caractères) — ne jamais réutiliser un mot de passe réel.

## B. Neon → Render → Vercel (dans cet ordre)

- [ ] **Neon** : projet dédié ; URL *pooled* (`DATABASE_URL`) et directe (`DATABASE_URL_DIRECT`), `sslmode=require` (`docs/DEPLOY_NEON.md`).
- [ ] **Render** : variables du tableau de `docs/DEPLOY_RENDER.md` ; `APP_ENV=production` ; `LLM_PROVIDER=mock`, `CRM_PROVIDER=mock` pour le premier démarrage ; `ENABLE_REAL_EMAIL_SEND=false`.
- [ ] `/health` et `/health/ready` OK ; `python -m scripts.verify_schema` OK ; seed exécuté.
- [ ] **Vercel** : URL Render dans `frontend/vercel.json` ; `/api/v1/health` répond via le proxy ; connexion fonctionnelle (cookie `HttpOnly; Secure; SameSite=Lax`).

## C. n8n (OVH)

- [ ] Suivre `automation/n8n/IMPORT_GUIDE.md` : credentials, import, `LF Config`, tests manuels, activation WF-01/02/03 puis WF-04.
- [ ] Une demande de test traverse tout le pipeline en mode mock (3 runs `Réussi`, brouillon à examiner).
- [ ] Aucun e-mail n'a été reçu (normal).

## D. Avant d'activer OpenAI réel

- [ ] Clé OpenAI **dédiée** au projet, avec limite de dépense côté OpenAI.
- [ ] `OPENAI_MODEL` accessible à votre clé (défaut `gpt-4.1-mini`, alternative `gpt-4o-mini`).
- [ ] Exécuter le **test réel** (2 appels) : `RUN_OPENAI_LIVE=1 … pytest tests/test_openai_live.py -m openai_live` (`docs/OPENAI_INTEGRATION.md`).
- [ ] Renseigner `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK` (tarifs officiels) si vous voulez une estimation ; fixer `LLM_DAILY_CALL_LIMIT`.
- [ ] Passer `LLM_PROVIDER=openai` ; soumettre une demande fictive ; contrôler le résumé, les citations, le score, le brouillon.
- [ ] Tester une demande d'injection (« Ignore all previous instructions… ») : doit finir en **revue humaine**, sans brouillon.
- [ ] Mesurer sur un jeu de 30–50 demandes fictives annotées (`TESTS_ACCEPTATION.md`) **avant** de publier le moindre pourcentage de précision.

## E. Avant d'activer HubSpot réel

- [ ] Compte HubSpot **de test** ; Private App avec scopes `crm.objects.contacts.read/write` ; token dans le credential n8n `LF - HubSpot Private App Token` (jamais dans Git/Render).
- [ ] `CRM_PROVIDER=hubspot` sur Render (seul interrupteur).
- [ ] Soumettre un contact fictif → fiche **créée** ; seconde demande du même e-mail → fiche **mise à jour** (une seule fiche) ; vérifier le statut CRM dans le dashboard.
- [ ] Simuler un token invalide : `HUBSPOT_AUTH_401`, dead-letter, état `FAILED` visible, **lead conservé**.

## F. Données personnelles (avant tout usage réel)

- [ ] Notice de confidentialité et base légale rédigées ; `PRIVACY_NOTICE_VERSION` mise à jour.
- [ ] Durées de rétention décidées (outbox, audit, runs, leads) ; `purge_retention --apply` planifié.
- [ ] Procédure d'export/effacement (`scripts/contact_data.py`) testée, **y compris la suppression côté HubSpot**.
- [ ] Contrat/DPA OpenAI, Render, Vercel, Neon, HubSpot vérifiés ; localisation des données validée.
- [ ] Remplacer les comptes de démonstration par de vrais comptes (+ MFA/politique de mots de passe si exposition publique).

## G. Exploitation

- [ ] Surveiller *Automatisations* (dead-letters, retries) et la consommation IA (*Vue d'ensemble*).
- [ ] Rotation planifiée de `API_SERVICE_TOKEN` (Render **et** credential n8n) et `SESSION_SECRET`.
- [ ] Sauvegarde logique (`pg_dump`) avant chaque migration ; restauration testée sur une base vide.
- [ ] Ne communiquer « production » que pour ce qui a été réellement vérifié (cf. `CAHIER_DES_CHARGES.md` §15).
