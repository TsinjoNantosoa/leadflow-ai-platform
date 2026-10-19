# Déploiement — workflows n8n sur l'instance OVH existante

> **Interdit à l'assistant** : aucun import, aucune activation, aucune modification de votre VPS ou de vos workflows n'a été faite. Ce document décrit ce que **vous** ferez après validation.

La procédure détaillée, pas à pas, est dans [`automation/n8n/IMPORT_GUIDE.md`](../automation/n8n/IMPORT_GUIDE.md). Résumé et contrôles d'isolation :

## Isolation de vos autres projets

- Les 4 workflows sont **nouveaux** et préfixés `LF-` ; l'import ne remplace rien (identifiants générés par n8n).
- Les 3 credentials sont nouveaux et préfixés `LF - ` ; n'en réutilisez aucun existant.
- Aucune variable d'environnement n8n à ajouter ni à modifier (la configuration passe par le nœud `LF Config` et les credentials) : **aucun redémarrage de n8n n'est requis**.
- Les webhooks ajoutés : `/webhook/lf-wf-01-lead-qualification`, `/lf-wf-02-crm-sync`, `/lf-wf-03-followup-draft` (authentifiés par en-tête). Aucun chemin existant n'est écrasé ; vérifiez qu'aucun de vos workflows n'utilise ces chemins.
- Charge ajoutée : ≈ 72 exécutions/jour de WF-04 (poll de récupération à 20 min, ~2 200/mois) + 1 réveil par soumission + exécutions des enfants uniquement quand un événement existe. Intervalle réglable (`build_workflows.py --poll-minutes N` ou nœud *Schedule Trigger*). Ne descendez pas à ~5 min : cela maintiendrait Render Free éveillé en permanence.

## Tableau des paramètres

| Quoi | Où | Valeur |
| --- | --- | --- |
| URL de l'API | `LF Config.api_base_url` (4 workflows) | `https://<service>.onrender.com/api/v1/internal` |
| URL de n8n | `LF Config.n8n_base_url` (WF-04) | URL publique ou boucle locale de votre n8n |
| Secret API | credential `LF - LeadFlow API Service Token` | `Authorization: Bearer <API_SERVICE_TOKEN>` |
| Secret webhook | credential `LF - n8n Webhook Secret` | en-tête `X-LeadFlow-Webhook-Secret` |
| Token HubSpot | credential `LF - HubSpot Private App Token` | uniquement si `CRM_PROVIDER=hubspot` |

## Ordre

1. Credentials → 2. Import des 4 JSON → 3. Éditer `LF Config` → 4. Test manuel (WF-04 *Execute workflow*) → 5. Activer WF-01/02/03 → 6. Activer WF-04 → 7. Vérifier le dashboard.

## Réseau

Render ne contacte **jamais** n8n (modèle *pull*) : aucune ouverture de port entrante n'est nécessaire sur le VPS pour l'API. Seul WF-04 appelle ses propres webhooks (boucle locale ou URL publique de n8n). Si vous exposez n8n publiquement, les webhooks `lf-wf-*` exigent déjà le secret d'en-tête.

## Rollback

Désactiver `LF-WF-04` suffit à tout arrêter sans perte (l'outbox conserve les événements). Suppression complète : voir `IMPORT_GUIDE.md` §8.
