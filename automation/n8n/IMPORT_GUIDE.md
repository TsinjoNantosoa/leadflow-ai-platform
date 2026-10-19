# Guide d'import sur votre instance n8n existante (OVH)

> **Rien n'a été importé ni activé par l'assistant.** Ce guide est à exécuter par vous, après validation de la livraison. Il n'altère aucun workflow existant : les quatre workflows sont **nouveaux**, préfixés `LF-`, livrés **désactivés**.

## 0. Prérequis

- n8n **≥ 1.100** (testé 2.43.8), accessible en HTTPS depuis Internet **uniquement si** vous exposez les webhooks ; ici les webhooks sont appelés par WF-04 sur **la même instance** (boucle locale possible).
- L'API FastAPI déployée (Render) et son `API_SERVICE_TOKEN` (Render → Environment).
- Aucune clé OpenAI nécessaire dans n8n.

## 1. Créer les credentials (Credentials → *Create credential*)

Créez-les **avant** l'import, avec **exactement ces noms** (ils rendent la réaffectation évidente) :

1. **`LF - LeadFlow API Service Token`** — type *Header Auth* : Name `Authorization`, Value `Bearer <API_SERVICE_TOKEN>`.
2. **`LF - n8n Webhook Secret`** — type *Header Auth* : Name `X-LeadFlow-Webhook-Secret`, Value = une longue valeur aléatoire (`openssl rand -base64 36`).
3. **`LF - HubSpot Private App Token`** — type *HubSpot App Token* : seulement si vous activez HubSpot (sinon créez-le avec une valeur factice : il n'est utilisé qu'en mode `hubspot`).

## 2. Importer les 4 workflows

Dans l'interface : *Workflows → ⋮ → Import from file*, pour chacun :
`WF-01-Lead-Qualification.json`, `WF-02-HubSpot-CRM-Sync.json`, `WF-03-Followup-Draft.json`, `WF-04-Operations-Recovery.json`.
(CLI équivalent : `n8n import:workflow --input=WF-0X-….json`.)

Après import, les nœuds portant un credential affichent un avertissement : **ouvrez chaque nœud HTTP Request / Webhook et sélectionnez le credential de même nom** (liste déroulante). Les workflows restent inactifs.

## 3. Adapter les paramètres (nœud « LF Config » de chaque workflow)

| Workflow | Champ | À mettre |
| --- | --- | --- |
| WF-01, 02, 03, 04 | `api_base_url` | `https://<service>.onrender.com/api/v1/internal` |
| WF-04 | `n8n_base_url` | URL de votre n8n, **sans** `/webhook` (ex. `https://n8n.mondomaine.tld`) |

Dans WF-04, WF-01/02/03 : *Settings → Error workflow* → sélectionnez `LF-WF-04 Operations Recovery` (alerte en cas d'erreur inattendue de nœud).

## 4. Tester chaque workflow séparément (avant d'activer WF-04)

Pré-test API : `curl https://<service>.onrender.com/api/v1/health` (réveille Render ; attendre ~1 min à froid).

1. **Soumettez une demande** via le formulaire `/demo` du frontend : un événement `LEAD_SUBMITTED` apparaît en base.
2. **WF-04** : ouvrez-le, bouton *Execute workflow* (Manual Trigger). Vérifiez : `Claim Events` → statut 200, `Split Events` → 1 élément, `Dispatch LF-WF-01` en erreur tant que WF-01 n'est pas actif (normal) — le backend replanifiera l'événement (`N8N_DISPATCH_FAILED`, retry avec backoff).
3. **Activez WF-01, WF-02, WF-03** (interrupteur *Active*), puis relancez WF-04 manuellement. Dans l'API : le lead passe `PROCESSING → QUALIFIED/READY`, des runs apparaissent dans **Automatisations**.

## 5. Ordre d'activation

1. `LF-WF-01`, `LF-WF-02`, `LF-WF-03` (les trois webhooks) — dans cet ordre ou non, mais **avant** WF-04.
2. `LF-WF-04` en dernier : il déclenche réellement les traitements toutes les minutes.

## 6. Vérifier après import

| Contrôle | Attendu |
| --- | --- |
| Dashboard → Automatisations | 3 runs `Réussi` par lead (qualification, CRM, brouillon) |
| Dashboard → Revue humaine | Un brouillon `Brouillon` à examiner |
| Lead → Parcours | 6 étapes terminées, « Revue humaine » en attente |
| n8n → Executions | Aucune exécution en erreur ; WF-04 chaque minute |
| Aucun e-mail reçu | Normal : il n'existe aucun envoi |

## 7. Passer en HubSpot réel (plus tard, après le test réel)

1. Créer une *Private App* HubSpot (scopes `crm.objects.contacts.read/write`), copier le token dans le credential `LF - HubSpot Private App Token`.
2. Sur Render : `CRM_PROVIDER=hubspot` (redéploiement). C'est **le seul** interrupteur : n8n lit le mode via l'API.
3. Tester avec **un contact fictif** dans un compte HubSpot de test, vérifier : création, puis seconde demande du même e-mail ⇒ **mise à jour** (une seule fiche), puis `RETRYING`/`FAILED` visibles dans le dashboard en cas d'erreur.

## 8. Rollback

- **Arrêt immédiat** : désactiver `LF-WF-04` (plus aucun événement n'est réservé ; l'outbox conserve tout, rien n'est perdu).
- **Retour arrière complet** : désactiver puis supprimer les 4 workflows `LF-*` et les 3 credentials `LF - *`. Vos autres workflows ne sont pas concernés.
- Les événements en cours reprennent automatiquement (lease expirée) à la réactivation. Un événement abandonné (*dead-letter*) se relance depuis **Automatisations → Reprise manuelle** (admin).
- Changer `API_SERVICE_TOKEN` côté Render **et** dans le credential `LF - LeadFlow API Service Token` si le secret a fuité.

## 9. Dépannage

| Symptôme | Cause probable |
| --- | --- |
| `Claim Events` : 401 `invalid_service_credentials` | Valeur du credential ≠ `API_SERVICE_TOKEN` (vérifier `Bearer ` + espace) |
| `Claim Events` : 401 `timestamp_stale` | Horloge du VPS décalée de plus de 5 min (NTP) |
| `Claim Events` : timeout | Render dort : la première exécution réveille (≈ 50 s) ; la suivante réussit |
| `Dispatch … : 403/404` | Workflow enfant inactif, ou secret de webhook différent entre WF-04 et l'enfant |
| `N8N_DISPATCH_FAILED` en boucle | `n8n_base_url` incorrecte |
| `HUBSPOT_AUTH_401` | Token HubSpot invalide/scope manquant (erreur de configuration : dead-letter direct) |
| `LLM_AUTH_ERROR` / `LLM_MODEL_UNAVAILABLE` | Côté Render : `OPENAI_API_KEY` / `OPENAI_MODEL` |
