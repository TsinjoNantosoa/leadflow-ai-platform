# Sécurité

## Modèle de menaces résumé

| Surface | Menace | Parade |
| --- | --- | --- |
| Formulaire public | Abus, spam, doublons, injection | Pydantic strict (`extra=forbid`, tailles, liens limités), honeypot, plafond par IP **hachée**/heure persistant en base, `Idempotency-Key` + empreinte, caractères de contrôle/NUL supprimés |
| Dashboard | Accès non autorisé, CSRF, vol de session | Sessions serveur : cookie `HttpOnly`, `Secure` en production, `SameSite=Lax`, jeton **haché** (HMAC) en base ; CSRF par jeton en en-tête + contrôle `Origin` ; verrouillage après échecs ; réponse identique que le compte existe ou non ; Argon2id |
| Endpoints internes | Appel anonyme, rejeu | Bearer comparé en temps constant, fail-closed sans secret, `X-LF-Timestamp` ±300 s, `Idempotency-Key` obligatoire, aucun accès par cookie |
| Texte du prospect | Injection de prompt | Donnée non fiable encadrée et déclarée telle ; sortie bornée au schéma ; heuristique d'injection indépendante ; revue humaine ; **aucun effet sur le score** (calculé hors LLM) ; rendu en **texte brut** dans le dashboard |
| Brouillons | Engagement/prix inventé, envoi involontaire | Prompt + politique de contenu deux fois ; **contrainte SQL** interdisant `SENT`/`READY_TO_SEND` ; aucun code d'envoi ; `ENABLE_REAL_EMAIL_SEND=true` est refusé au démarrage |
| Données | Fuite, rétention | Minimisation (seuls message + indication de service vont à OpenAI), `store=False`, pas de PII dans l'outbox ni les logs, rétention scriptée, export/effacement par contact |

## Autorisations

| Action | ADMIN | SALES | Anonyme |
| --- | :-: | :-: | :-: |
| Lire leads, métriques, runs, brouillons | ✔ | ✔ | ✘ (401) |
| Modifier / approuver / rejeter un brouillon | ✔ | ✔ | ✘ |
| Relancer un lead | ✔ | ✔ | ✘ |
| Reprise manuelle d'un événement (dead-letter) | ✔ | ✘ (403) | ✘ |
| Endpoints `/internal/*` | via jeton de service uniquement | | |

Les rôles sont appliqués **côté serveur** sur chaque endpoint ; masquer un bouton dans React n'est jamais la protection (tests : un commercial qui forge l'appel reçoit `403`).

## Cookies Vercel ↔ Render

Domaines différents = cookies tiers (bloqués par certains navigateurs). **Parade retenue** : `vercel.json` réécrit `/api/*` vers Render ; le navigateur ne parle qu'à l'origine Vercel (cookie first-party, aucun CORS). Repli : `SESSION_COOKIE_SAMESITE=none` (HTTPS obligatoire, validé au démarrage) + `CORS_ALLOWED_ORIGINS` strict. Aucun jeton n'est stocké dans `localStorage`/`sessionStorage` (vérifié par test E2E) ; le jeton CSRF reste en mémoire.

## Secrets

- Aucun secret dans Git (`.gitignore` : `.env*` sauf `.env.example`), ni dans le frontend (seules `VITE_API_BASE_URL`, `VITE_APP_NAME`, `VITE_APP_ENV` existent), ni dans les exports n8n (credentials par *placeholder*), ni dans les tests (clés fictives).
- Les secrets sont des `SecretStr` : absents des `repr()`/logs ; les erreurs OpenAI ne contiennent jamais la clé (testé).
- Production : `SESSION_SECRET` et `API_SERVICE_TOKEN` ≥ 32 caractères aléatoires, imposés au démarrage. Générer : `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- Rotation : changer `API_SERVICE_TOKEN` dans Render **et** dans le credential n8n ; changer `SESSION_SECRET` invalide toutes les sessions.

## En-têtes et exposition

Backend : `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`. Frontend (Vercel) : CSP stricte (`default-src 'self'`, pas de script inline), `frame-ancestors 'none'`, `Permissions-Policy` restrictive. Swagger/OpenAPI désactivés en production.

## Journalisation

Logs JSON structurés avec `correlation_id` ; **jamais** de corps de requête, de message de prospect, d'e-mail ni de secret (les erreurs de validation ne renvoient pas les valeurs saisies).

## Limites connues (à traiter avant un usage réel)

- Pas de MFA ni de réinitialisation de mot de passe (comptes de démonstration).
- Le rate limit public repose sur l'IP lue dans `X-Forwarded-For` (`TRUST_PROXY_HEADERS`) : à durcir derrière un proxy de confiance connu.
- La rétention de l'audit et des runs n'est pas automatisée (décision métier requise).
- La suppression d'un contact n'efface pas la fiche HubSpot.
- Le calendrier de rétention, la notice de confidentialité et la base légale doivent être validés avant tout traitement de données réelles.
