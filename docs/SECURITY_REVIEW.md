# Revue de sécurité (V1.1)

## Protections vérifiées par des tests exécutés
| Domaine | Protection | Preuve |
| --- | --- | --- |
| Sessions | jeton aléatoire, **hash** en base, cookie `HttpOnly`, `Secure` en production, `SameSite=Lax`, aucun jeton dans `localStorage` | `test_dashboard_auth`, E2E « cookie HttpOnly » |
| CSRF | en-tête sur toute mutation + contrôle `Origin` | `test_dashboard_auth` |
| CORS | liste stricte (`FRONTEND_URL` + `CORS_ALLOWED_ORIGINS`) | `test_dashboard_auth` |
| Authentification | Argon2, message générique, verrouillage après échecs | `test_dashboard_auth`, E2E |
| Rôles | `SALES` ne peut pas relancer une exécution (403) | `test_T16_*`, E2E |
| Interne n8n | jeton Bearer + horodatage ±300 s, fail-closed, `Idempotency-Key`, tentative obsolète ignorée | `test_T14_*`, `test_T15_*`, `test_outbox` |
| Public | validation Pydantic, honeypot, plafond par IP hachée, idempotence, erreurs sans écho des données | `test_public_api` |
| Envoi d'e-mail | impossible : aucune fonction d'envoi + CHECK en base + `ENABLE_REAL_EMAIL_SEND` refuse `true` | `test_T11/T12`, `test_database` |
| Journaux | JSON, `correlation_id`, ni corps ni PII ni secret | `test_units` |
| Secrets | scan des fichiers suivis : aucun ; `.env` ignorés ; contrôles en production | scan + `test_units` |

## Corrigé en V1.1
**`TRUST_PROXY_HEADERS`** : la V1 prenait la **première** entrée de `X-Forwarded-For`, que le client contrôle (envoyer `X-Forwarded-For: 1.2.3.4` suffisait à échapper au plafond par IP). Désormais : lecture depuis la **droite** (`TRUSTED_PROXY_HOPS`, défaut 1) ; si l'en-tête est plus court que prévu, repli sur l'IP de connexion. Tests : spoof à gauche ignoré, 2 sauts, en-tête court, proxy non fiable.
**Premier administrateur** : `scripts/create_admin.py` (plus besoin des comptes démo en production).

## Risques restants
1. Derrière le rewrite Vercel, l'IP vue par Render peut être celle de Vercel pour tous les visiteurs ; le nombre exact de sauts est à vérifier au premier déploiement. Pire cas : plafond partagé (plus strict, pas contournable).
2. Anti-abus par IP et verrouillage de compte, sans CAPTCHA : un attaquant distribué reste possible → envisager un CAPTCHA avant exposition publique.
3. Pas de MFA ; comptes démo à désactiver en production.
4. RGPD : notice de confidentialité, rétention, effacement HubSpot, DPA fournisseurs **non réalisés** (`RELEASE_CHECKLIST.md` §F).
5. Rewrite Vercel et cookies en conditions réelles : non testés.
6. Aucun test d'intrusion ; revue interne uniquement.
