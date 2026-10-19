# Déploiement — frontend React sur Vercel

> Préparation uniquement. **Rien n'a été déployé.**

## Pourquoi un rewrite `/api` ?

Frontend (Vercel) et API (Render) sont sur des **domaines différents**. Un cookie de session posé par l'API serait un cookie *tiers*, bloqué par de nombreux navigateurs. `frontend/vercel.json` réécrit donc `/api/*` vers Render : le navigateur ne parle qu'à `https://<projet>.vercel.app` (cookie *first-party*, `SameSite=Lax`, aucun CORS). Les tokens ne sont jamais stockés dans `localStorage`.

## 1. Configuration du projet

| Paramètre | Valeur |
| --- | --- |
| Framework | Vite |
| Root Directory | `frontend` |
| Install | `npm ci` |
| Build | `npm run build` (exécute `tsc -b` puis `vite build`) |
| Output | `dist` |
| Node | ≥ 20.19 |

Déjà définis dans `frontend/vercel.json`.

## 2. Renseigner l'origine de l'API (une commande, une seule fois)

Les destinations de `rewrites` ne supportent pas les variables d'environnement. `frontend/vercel.json` contient donc le jeton `__RENDER_API_ORIGIN__`, remplacé par **votre** URL Render (publique, pas un secret) :

```bash
cd frontend
npm run configure:vercel -- https://<votre-service>.onrender.com    # valide : https, sans chemin, pas d'URL factice/locale
git diff vercel.json                                                 # vérifiez, puis committez
```
Garde-fou : `npm run build` exécute d'abord `vercel-config.mjs --check`, qui **fait échouer le build sur Vercel** (`VERCEL=1`) si le jeton est encore présent — aucun déploiement ne peut partir avec une URL inventée. En local, le build n'est pas bloqué.

Le second `rewrite` (`/((?!api/|assets/|favicon.svg).*) → /index.html`) fournit le **fallback SPA** : `/app/leads/123` et `/login` fonctionnent en accès direct et au rechargement.

## 3. Variables publiques (Settings → Environment Variables)

| Variable | Valeur | Rôle |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api` *(défaut)* | Base des appels. À changer uniquement pour un appel direct cross-origin (`https://<api>/api`, exige `SESSION_COOKIE_SAMESITE=none` + CORS) |
| `VITE_APP_NAME` | `LeadFlow AI` | Libellé |
| `VITE_APP_ENV` | `production` | Libellé |

**Aucune clé OpenAI, aucun secret** : tout ce qui est préfixé `VITE_` est publié dans le bundle.

## 4. En-têtes de sécurité

`vercel.json` applique : CSP stricte (`default-src 'self'`, pas de script inline — le thème s'initialise via `/theme-init.js`), `X-Frame-Options: DENY`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, cache immuable sur `/assets/*`.

## 5. Cold start de Render

Le premier appel après inactivité peut prendre ~1 min. Le frontend : (1) réveille l'API à l'ouverture de `/demo` ; (2) tolère 60 s de latence et reprend 2 fois sur 502/503/504 (lectures et écritures idempotentes uniquement) ; (3) affiche « Serveur injoignable… réessayez » sans jamais perdre la saisie. Si les rewrites Vercel vers un service endormi expiraient trop tôt dans votre cas, la solution de repli est l'appel direct documenté ci-dessus.

## 6. Contrôles après déploiement

1. `https://<projet>.vercel.app/app/runs` (accès direct) → redirige vers `/login` (SPA + garde de session).
2. `https://<projet>.vercel.app/api/v1/health` → `{"status":"ok"}` (proxy fonctionnel).
3. Connexion → cookie `lf_session` `HttpOnly; Secure; SameSite=Lax` (DevTools › Application).
4. `/demo` → soumission → identifiant de demande.

## 7. Ce qui n'est **pas** vérifié

Le rewrite Vercel → Render n'a pas pu être exécuté localement (nécessite un projet Vercel). Le comportement « même origine + cookie first-party » est validé par le proxy Vite de développement et Playwright, pas par Vercel. À contrôler à la première mise en ligne (section 6). **Retour arrière** : *Deployments → Promote* du déploiement précédent.

## 8. Indépendance

`frontend/` n'importe aucun code Python ni fichier du backend ; il peut être extrait dans son propre dépôt tel quel (`package.json`, `package-lock.json`, `vercel.json`, `.env.example`).
