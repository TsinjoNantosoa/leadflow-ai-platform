# Rapport de tests — LeadFlow AI V1

Date d'exécution : 2026-10-19 · Machine locale Windows 11 · PostgreSQL 16 (Docker) · Python 3.12 · Node ≥ 20.19 · n8n 2.43.8 (Docker jetable).
Tous les chiffres ci-dessous sont **mesurés** lors de cette exécution. Légende : ✅ exécuté et réussi · ⏭ ignoré volontairement · ⛔ non exécutable ici (raison donnée).

## 1. Résultats mesurés

| Contrôle | Résultat |
| --- | --- |
| Backend `ruff check .` | ✅ aucun problème |
| Backend `pytest` (PostgreSQL réel, base `*_test` jetable) | ✅ **248 réussis, 2 ignorés, 0 échec** (≈ 6 min) — mesure V1.1 ; 237 avant les ajouts V1.1 |
| Backend `alembic check` / `scripts.verify_schema` | ✅ modèles = migration 0001, aucun écart |
| Frontend `tsc -b --noEmit` | ✅ |
| Frontend ESLint | ✅ 0 erreur |
| Frontend Vitest + RTL | ✅ **78/78** (trois passages complets consécutifs en V1.1) |
| Frontend `npm run build` | ✅ |
| `npm audit --omit=dev` | ✅ 0 vulnérabilité |
| Playwright (Chromium, vrai backend + PostgreSQL + dev_worker) | ✅ **12 réussis**, 1 ignoré (captures, activées par `E2E_SCREENSHOTS=1`, puis exécutées avec succès : `docs/screenshots/`) |
| Build Docker backend (`docker build`) | ✅ ; conteneur démarré sur base jetable : migrations auto, `/health` et `/health/ready` OK, utilisateur non root |
| n8n 2.43.8 local : import + publication des 4 workflows | ✅ |
| n8n local : chaîne WF-04 → WF-01 → WF-02 → WF-03 (mock) | ✅ lead `READY`, 3 événements livrés, 3 exécutions réussies |
| n8n local + **faux** HubSpot : 7 scénarios | ✅ création · mise à jour sans doublon · 429 puis succès · timeout après succès sans second contact · 401 → dead-letter · LLM invalide → revue manuelle · panne LLM → retry |
| V1.1 : `validate_workflows.py` (4 workflows) | ✅ 4 OK |
| V1.1 : migrations sur base vierge (`upgrade head` ×2, `alembic check`, `verify_schema`, `create_admin` ×2) | ✅ idempotent, 15 tables, 6 garde-fous |
| V1.1 : Playwright après modifications | ✅ 12 réussis, 1 ignoré |
| Scan de secrets (fichiers suivis par git) | ✅ aucun secret réel |

Note d'honnêteté : le test Vitest « connexion réussie » a échoué par intermittence en suite complète (2 passages sur 4) : première importation paresseuse du chunk *Vue d'ensemble* (recharts) plus lente que le délai de 5 s sous exécution parallèle. Cause identifiée, délai de **cette** attente porté à 15 s ; 3 passages complets ensuite sans échec. Aucun test supprimé.

## 2. Correspondance avec T01–T20

| Test | Couverture | Statut |
| --- | --- | --- |
| T01 lead complet | `test_T01_complete_lead_is_persisted_with_outbox_event` | ✅ |
| T02 budget absent → null | `test_T02_no_budget_means_null_not_invented` + `test_scoring` | ✅ |
| T03 idempotence | `test_T03_*` (clé rejouée, e-mail normalisé) + E2E double clic | ✅ |
| T04 même clé, corps différent | `test_T04_same_key_different_body_is_409_and_audited` | ✅ |
| T05 même contact, deux leads | `test_T05_*` | ✅ |
| T06 normalisation e-mail | `test_T06_*` | ✅ |
| T07 payloads invalides | `test_T07_*` | ✅ |
| T08 sortie LLM invalide / refus | `test_T08_*` | ✅ (fournisseur mock + client OpenAI sur transport simulé) |
| T09 CRM indisponible | `test_T09_*` + n8n/faux HubSpot (scénarios C, E) | ✅ |
| T10 succès puis timeout | `test_T10_*` + n8n/faux HubSpot (scénario D) | ✅ |
| T11 brouillon, aucun envoi | `test_T11_*` + contrainte CHECK en base (`test_database`) | ✅ |
| T12 approbation sans envoi | `test_T12_*` + E2E | ✅ |
| T13 anonyme refusé | `test_T13_*` + E2E sécurité | ✅ |
| T14 jeton de service | `test_T14_*` | ✅ |
| T15 callbacks rejoués | `test_T15_*`, `test_outbox` | ✅ |
| T16 reprise / dead-letter / rôles | `test_T16_*` + E2E rôles | ✅ |
| T17 injection de prompt | `test_T17_*` | ✅ (heuristique + schéma strict ; **non mesuré sur un vrai modèle**) |
| T18 mobile / clavier / a11y | Playwright `responsive-a11y.spec.ts` (375 px, clavier, thème) | ✅ |
| T19 parcours complet | `test_T01_T19_full_pipeline_with_mock_providers` + E2E `pipeline.spec.ts` | ✅ (mock) |
| T20 build / lint / tests | §1 | ✅ |

## 3. Non exécuté — à ne pas présenter comme validé

| Élément | Statut | Raison |
| --- | --- | --- |
| OpenAI **réel** (`test_openai_live.py`, 2 tests) | ⏭ ignorés | aucune clé fournie, appels payants interdits sans activation explicite. Le client est exercé uniquement contre le SDK officiel avec un transport httpx **simulé**. |
| HubSpot **réel** | ⛔ | aucun compte/jeton ; seule la branche a été exécutée contre un **faux** serveur local. |
| Import sur le n8n **OVH** | ⛔ | interdit sans accord ; validé uniquement sur n8n local jetable. |
| Déploiements Vercel / Render / Neon distant | ⛔ | interdits sans accord ; configurations préparées, jamais exécutées. |
| Qualité réelle d'extraction (précision, coût, latence) | ⛔ | nécessite un vrai modèle et un jeu annoté de 30–50 demandes ; aucun pourcentage n'est revendiqué. |
| Test de charge, Safari/Firefox, lecteur d'écran réel | ⛔ | hors périmètre de cette exécution (Chromium seulement ; contrôles d'accessibilité automatisés + clavier). |

## 4. Ajouts V1.1 (tests nouveaux, tous exécutés et réussis)
`backend/tests/test_v11_hardening.py` (11) : IP derrière proxy (non fiable, spoof à gauche, 2 sauts, en-tête court) · réveil n8n (désactivé par défaut, en-tête secret sans donnée métier, **n8n injoignable sans effet sur la soumission**, un seul appel à la création / aucun au rejeu) · `create_admin` idempotent et mot de passe court refusé · smoke OpenAI refusé sans activation explicite / sans clé. `test_dashboard_auth` : indicateurs `automation_performance`. `frontend/tests/unit/vercel-config.test.ts` (7).

## 5. Scénarios de résilience demandés (V1.1 §12)
| # | Scénario | Couverture exécutée |
| --- | --- | --- |
| 1 | OpenAI indisponible | `test_T16_llm_timeout_is_retried…` (lead conservé, reprise planifiée) |
| 2 | HubSpot 429 | n8n local + faux HubSpot (scénario C) ; backoff : `test_retry_after_is_respected`, `test_backoff_grows_exponentially_and_is_capped` |
| 3 | n8n ne répond pas | `test_scenario3_n8n_down…`, `test_expired_lease_is_recovered_after_crash` |
| 4 | Render redémarre | `test_expired_lease_is_recovered_after_crash`, `test_lease_expiry_exhausts_attempts_into_dead_letter…` (état en base, pas en mémoire) |
| 5 | Double soumission | `test_parallel_double_click_same_key_creates_exactly_one_lead`, E2E double clic |
| 6 | Double callback | `test_T15_*`, `test_stale_attempt_callback_is_ignored` |
| 7 | Brouillon rejeté | `test_parallel_approve_and_reject_exactly_one_wins`, `test_T11/T12` (aucun envoi possible) |
| 8 | Données IA invalides | `test_T08_*` |
| 9 | Deux workers, même événement | `test_concurrent_claims_never_return_same_event` |
| 10 | Réveil de Render | Vitest `api.test.ts` (reprise sur 503, jamais de mutation sans clé d'idempotence, même clé au rejeu) ; **réveil réel de Render non reproductible localement** |
