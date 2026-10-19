# LeadFlow AI — frontend

SPA **React 19 + TypeScript (strict) + Vite + Tailwind CSS 4**, composants de type shadcn/ui (Radix), React Router, TanStack Query, React Hook Form + Zod, Recharts, Lucide. Application **autonome** : aucun import du backend, déployable seule sur Vercel.

## Pages

| Route | Page | Accès |
| --- | --- | --- |
| `/` | Landing (présentation, fonctionnalités, architecture, cas NovaDigital) | public |
| `/demo` | Formulaire de demande (validation, consentements, idempotence, confirmation) | public |
| `/login` | Connexion (session serveur) | public |
| `/app/overview` | Indicateurs calculés depuis PostgreSQL | session |
| `/app/leads` | Liste : recherche, filtres (dans l'URL), tri, pagination | session |
| `/app/leads/:id` | Détail : demande, extraction IA, score explicable, CRM, brouillon, traitements, audit, **timeline** | session |
| `/app/reviews` | Revue humaine : modifier / approuver / rejeter, historique | session |
| `/app/runs` | Monitor des automatisations (reprise manuelle : admin) | session |

La sécurité réelle est appliquée par l'API ; les gardes React (`RequireAuth`) ne sont qu'un confort d'interface.

## Démarrage

```bash
cd frontend
cp .env.example .env          # optionnel (valeurs par défaut valables en dev)
npm ci
npm run dev                   # http://localhost:5173 — proxy /api -> http://localhost:8000
```
Il faut le backend (`cd backend && uvicorn app.main:app --port 8000`) et une base migrée/seedée (voir `backend/README.md`).

## Variables (`.env.example`)

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` | Base des appels (proxy de même origine) |
| `VITE_APP_NAME`, `VITE_APP_ENV` | `LeadFlow AI`, `development` | Libellés |
| `DEV_API_PROXY_TARGET` | `http://localhost:8000` | Cible du proxy `dev`/`preview` (hors bundle) |

## Qualité

```bash
npm run typecheck   # tsc -b --noEmit (strict, noUncheckedIndexedAccess)
npm run lint        # ESLint (0 erreur attendue)
npm test            # Vitest + React Testing Library (jsdom)
npm run build       # tsc -b && vite build -> dist/
npm run e2e         # Playwright (voir ci-dessous)
```

### Tests end-to-end (Playwright)

Démarrent un **vrai** backend (mock LLM/CRM) sur `:8011` avec une base PostgreSQL jetable `leadflow_playwright`, et le frontend compilé sur `:4173`. Pré-requis : `docker compose up -d db` à la racine, `backend/.venv` créé, `npx playwright install chromium`. Le rôle de n8n est tenu par `backend/scripts/dev_worker.py` (mêmes appels HTTP que les workflows). Variables : `E2E_DATABASE_URL`, `E2E_BACKEND_PYTHON`, `E2E_API_PORT`, `E2E_WEB_PORT`.

## Déploiement Vercel

Voir [`docs/DEPLOY_VERCEL.md`](../docs/DEPLOY_VERCEL.md). Une seule édition obligatoire : l'URL Render dans `vercel.json` (`rewrites`). Le fallback SPA et les en-têtes de sécurité (CSP stricte) sont déjà configurés.

## Choix de conception

- **Accessibilité** : lien d'évitement, focus visibles, `aria-invalid`/`role="alert"` sur les erreurs, `aria-sort`, timeline en liste ordonnée avec états annoncés, `prefers-reduced-motion` respecté, select natifs (clavier/mobile).
- **Honnêteté des données** : aucun chiffre en dur dans le dashboard ; les données de démonstration sont signalées (`DÉMO`, bandeau) ; la timeline n'affiche « terminé » que pour des enregistrements existants.
- **Cold start** : réveil de l'API à l'ouverture du formulaire, timeouts généreux, reprises limitées et sûres (jamais d'écriture sans `Idempotency-Key`).
- **XSS** : le texte des prospects est rendu en texte brut ; aucun `dangerouslySetInnerHTML`.
- **Thème** clair/sombre persistant, appliqué avant le premier rendu (script externe, compatible CSP).
