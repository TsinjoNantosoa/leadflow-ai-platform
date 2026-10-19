# Audit V1 → V1.1

Périmètre inspecté : `frontend/`, `backend/` (modèles, migration 0001, services, tests, Dockerfile, `render.yaml`), `automation/n8n/`, `docs/`, configurations de déploiement. Méthode : lecture + exécution des suites. Constat factuel, sans réécriture de ce qui fonctionne.

| # | Constat | Gravité | Traitement V1.1 |
| --- | --- | --- | --- |
| 1 | `docs/TEST_REPORT.md` absent à l'issue de la V1 | Documentation | Créé après exécution (chiffres mesurés) |
| 2 | WF-04 sondait **toutes les minutes** : ~43 000 exécutions n8n/mois, et Render Free ne dormirait jamais | Coût / déploiement | Poll de récupération **20 min** (réglable) + **réveil best-effort** par le backend (webhook `lf-wf-04-wake`) après chaque soumission |
| 3 | `TRUST_PROXY_HEADERS=true` lisait la **première** entrée de `X-Forwarded-For`, fournie par le client donc falsifiable (contournement du plafond par IP) | Sécurité | Lecture depuis la **droite** avec `TRUSTED_PROXY_HOPS`, repli sur l'IP de connexion si l'en-tête est trop court ; 4 tests |
| 4 | Guide Render : seed par « Shell Render » (indisponible sur Free) ; seul moyen de créer des utilisateurs = comptes démo | Déploiement / sécurité | Procédure depuis le poste (Alembic + `verify_schema`), `scripts/create_admin.py` (idempotent, mot de passe ≥ 12, sans donnée démo), procédure de récupération |
| 5 | `vercel.json` : URL placeholder `YOUR-RENDER-SERVICE…` pouvant partir en production | Déploiement | Jeton `__RENDER_API_ORIGIN__` + `npm run configure:vercel -- <origine>` (validation https / sans chemin / non factice) + garde `prebuild` qui **échoue sur Vercel** si le jeton subsiste ; 7 tests |
| 6 | Pas de smoke test OpenAI réel dédié (seulement des tests pytest marqués) | Fonctionnel | `scripts/openai_smoke.py` : désactivé par défaut, plafond dur 4 appels, vérification gratuite du modèle, clé jamais affichée ; 2 tests |
| 7 | Tableau de bord sans durée de traitement ni nombre de reprises | Observabilité | `automation_performance` (durée moy./p95, reprises cumulées, dead-letters) : API + UI + tests |
| 8 | Pas de CI | Qualité | `.github/workflows/ci.yml` (backend + migrations sur base vierge, frontend, validation n8n, scan de secrets). **Non exécutée** (aucun push) |
| 9 | Pas de validateur statique des workflows | Qualité | `automation/n8n/tools/validate_workflows.py` (aussi utilisé par la CI) |
| 10 | Disponibilité de `gpt-4.1-mini` non vérifiée contre la doc officielle | Intégration | **Non vérifiable ici** (voir `OPENAI_VALIDATION.md`) ; vérification gratuite incluse dans le smoke test |
| 11 | Rewrite Vercel → Render jamais exécuté sur Vercel | Risque résiduel | Documenté comme non vérifié ; contrôles post-déploiement fournis |

Points vérifiés **corrects** et conservés : outbox transactionnelle + `SKIP LOCKED` + lease + backoff + dead-letter ; idempotence publique et interne ; contrainte CHECK interdisant `SENT`/`READY_TO_SEND` ; cookies HttpOnly + CSRF + Origin ; `pool_pre_ping`, `prepare_threshold=None` (Neon poolé), URL directe pour Alembic ; aucun worker permanent dans FastAPI ; workflows désactivés, préfixés `LF-`, sans secret ni nœud d'envoi d'e-mail.

Non réalisable ici et **documenté comme tel** : OpenAI/HubSpot réels, import OVH, déploiements.
