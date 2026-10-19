# Validation des workflows n8n (V1.1)

Fichiers (noms réels vérifiés) : `automation/n8n/WF-01-Lead-Qualification.json`, `WF-02-HubSpot-CRM-Sync.json`, `WF-03-Followup-Draft.json`, `WF-04-Operations-Recovery.json`.

## Validation statique (exécutée)
`python automation/n8n/tools/validate_workflows.py` → 4 OK : JSON valide · nom `LF-…` · `active:false` · connexions vers des nœuds existants · noms uniques · aucun nœud d'e-mail · aucun `retryOnFail` · webhooks `lf-…` uniques et authentifiés par en-tête · credentials limités aux 3 placeholders `LF - …` · aucun motif de secret · aucun `$env`.

## Validation sur n8n réel local (2.43.8, Docker jetable, port 5679)
- **V1 (exécuté)** : import/publication des 4 workflows ; chaîne WF-04 → 01 → 02 → 03 en mock ; 7 scénarios HubSpot contre un **faux** HubSpot (création, mise à jour sans doublon, 429 → succès, timeout après succès sans doublon, 401 → dead-letter, LLM invalide → revue, panne LLM → reprise).
- **V1.1 (exécuté)** : le WF-04 **modifié** (poll 20 min + webhook de réveil) s'importe sans erreur dans n8n 2.43.8.
- **V1.1 (non ré-exécuté)** : la chaîne complète déclenchée par le webhook de réveil sur n8n local, et la ré-exécution des 7 scénarios (ils ont tourné avec l'ancien déclencheur ; le reste du graphe WF-04 est inchangé). Le réveil est couvert côté backend (un appel à la création, aucun au rejeu, n8n injoignable sans effet sur la soumission) mais pas par une exécution n8n de bout en bout.

## Politique de déclenchement
Réveil best-effort (backend → `/webhook/lf-wf-04-wake`, en-tête `X-LeadFlow-Webhook-Secret`) + poll de récupération (20 min ; `build_workflows.py --poll-minutes N` ou édition du nœud). Le réveil ne porte aucune donnée ; WF-04 réserve via `POST /internal/outbox/claim` (atomique, lease). Plusieurs réveils simultanés sont sûrs (`SKIP LOCKED`). Le backend reste l'unique autorité des retries.

## Isolation OVH
Préfixe `LF-`, chemins de webhook `lf-wf-0X-…` (aucun chemin générique), credentials dédiés, workflows inactifs, aucun e-mail. **Non vérifié** : l'absence de conflit avec vos workflows existants (aucun accès à l'instance). Contrôlez vos chemins de webhook existants avant import (`IMPORT_GUIDE.md`).

## Compatibilité
Validé sur 2.43.8 uniquement ; la version de votre instance OVH est inconnue. Si elle diffère notablement, l'import peut signaler des versions de nœuds à ajuster.
