# LeadFlow AI — Plan des workflows n8n

Ces workflows sont des **spécifications à implémenter**, pas des exports n8n déjà exécutables.

## WF-01 — Lead Qualification Pipeline

**Déclenchement** : HTTP Webhook privé appelé par le dispatcher outbox (`LEAD_SUBMITTED`). Pas de webhook n8n public depuis le navigateur.

Noeuds n8n proposés :

1. **Webhook** : recevoir `event_id`, `lead_id`, `correlation_id`, sans PII dans les métadonnées de traçage.
2. **HTTP Request** vers FastAPI interne : obtenir données minimisées du lead, authentification backend.
3. **IF / Switch** : vérifier si le lead est déjà qualifié ; le traitement doit être idempotent.
4. **LLM call** : extraction JSON suivant le schéma versionné ; modèle paramétrable.
5. **Code / IF** : vérifier la structure et les champs obligatoires (validation finale en backend).
6. **HTTP Request** `POST /api/v1/internal/leads/{id}/qualification` : enregistrer extraction, score serveur et score_explanation.
7. **HTTP Request** : enregistrer le statut du run, lancer événement logique CRM_SYNC_REQUESTED.
8. **Respond to Webhook** : accusé de réception ; l'accusé HTTP ne signifie pas que tous les traitements métier sont terminés.

**Chemin d'échec** : refus LLM/sortie incorrecte/timeout => marquer revue manuelle, log corrélé, pas d'envoi.

## WF-02 — HubSpot CRM Sync

**Déclenchement** : événement `CRM_SYNC_REQUESTED`, traité après qualification (peut être appelé par un sous-workflow).

1. Webhook/Execute Workflow Trigger.
2. HTTP Request : récupérer contact et `crm_mappings` depuis backend ; seul le service backend accède à Postgres métier.
3. Switch `CRM_PROVIDER` : `mock` ou `hubspot`.
4. Mode HubSpot : recherche par e-mail normalisé / identifiant externe déjà enregistré ; si trouvé update, sinon create contact (idempotence).
5. HTTP Request : enregistrer résultat + external_contact_id auprès du backend.
6. HTTP Request : déclencher événement `DRAFT_REQUESTED`.

**Cas métier** : HTTP 429/5xx => retry avec backoff ; HTTP 401/403 => erreur de configuration + alerte ; pas de création répétée au retour d'un timeout.

## WF-03 — Follow-up Draft Generator

**Déclenchement** : `DRAFT_REQUESTED` après qualification ; synchronisation CRM non indispensable pour rédiger un brouillon.

1. Trigger depuis outbox ou workflow parent.
2. HTTP Request : récupérer détails nécessaires au brouillon.
3. LLM : générer sujet + réponse personnalisée, courte, factuelle, respectueuse de la langue et des informations fournies.
4. Validation JSON + politique : aucune promesse de prix/délai inventée, pas de contenu externe suspect, pas d'auto-envoi.
5. HTTP Request : `POST /api/v1/internal/leads/{id}/followups` (idempotent par id d'événement), statut `DRAFT`.
6. Notification interne optionnelle : « nouveau brouillon à examiner ».

**Après approbation** : FastAPI passe `DRAFT -> APPROVED`. Le MVP s'arrête ici. L'envoi réel est réservé à la V2, avec consentement, provider, désinscription et action explicite.

## WF-04 — Operations / Recovery

**Déclenchement** : Schedule Trigger à intervalle raisonnable et Error Trigger n8n dédié.

1. Schedule Trigger : demander au backend les événements outbox prêts pour retry (ou utiliser uniquement le dispatcher backend).
2. Code/IF : différencier erreur temporaire, permanente et données invalides.
3. HTTP Request : mettre à jour statut, attempt_count et error_code.
4. Notification interne si délai dépassé ou dead-letter.
5. Reprise manuelle après correction des credentials/données ; ne pas déclencher une boucle infinie.

**Important :** choisir une unique autorité des retries par événement (dispatcher backend recommandé) pour éviter n8n + backend qui réessaient indépendamment et doublent les effets.

## Convention d'événements

- `LEAD_SUBMITTED`
- `LEAD_QUALIFIED`
- `CRM_SYNC_REQUESTED`
- `CRM_SYNCED`
- `DRAFT_REQUESTED`
- `DRAFT_CREATED`
- `DRAFT_APPROVED`
- `AUTOMATION_FAILED`

Champs transversaux : `event_id`, `event_type`, `organization_id`, `lead_id`, `correlation_id`, `occurred_at`, `schema_version`.

## Sécurité et observabilité

- Un secret dédié aux appels serveur-vers-n8n, stocké côté serveur.
- Les workflows et credentials ne sont jamais exposés aux utilisateurs du dashboard.
- Service account / scope minimal pour HubSpot ; token jamais journalisé.
- Pas de PII complète dans les logs de workflow, ni de donnée clients réels dans le dépôt.
- Tester rejouabilité de chaque workflow et comportement après coupure réseau.
- Documenter le nombre d'exécutions, les échecs et les durées mesurées.

## Limites de licence

Self-hosted Community n8n est généralement adapté si seuls les membres de votre équipe contrôlent les workflows. Donner aux clients un éditeur de workflows ou une fonctionnalité de construction d'automatisations peut nécessiter une licence commerciale selon les conditions officielles n8n.
