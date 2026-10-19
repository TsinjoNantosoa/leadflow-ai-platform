# LeadFlow AI — Plan de test et critères d'acceptation

Les scénarios utilisent exclusivement des identités et sociétés fictives (`example.org`).

| Test | Donnée ou perturbation | Comportement attendu |
| --- | --- | --- |
| T01 | Prospect complet, service connu | Lead persisté, score motivé, brouillon créé |
| T02 | Prospect sans budget | `budget_amount = null`, aucun budget inventé |
| T03 | Idempotency-Key rejouée, même body | Même lead_id, aucune demande doublonnée |
| T04 | Idempotency-Key rejouée, body différent | HTTP 409, journal d'erreur métier |
| T05 | Même e-mail, nouvelle demande | Un contact, deux leads distincts |
| T06 | Même e-mail avec majuscules/espaces | Même contact normalisé |
| T07 | Texte très long / invalide | Validation 422 ou limite adaptée |
| T08 | Sortie LLM JSON incorrecte / refus | MANUAL_REVIEW, pas de crash ni d'envoi |
| T09 | HubSpot indisponible / 429 | Retry contrôlé, lead conservé en PostgreSQL |
| T10 | HubSpot retourne succès puis timeout réseau | Reprise sans créer second contact CRM |
| T11 | Brouillon créé | Aucun e-mail expédié automatiquement |
| T12 | Commercial approuve | Statut APPROVED, audit ; pas de passage SENT |
| T13 | Visiteur anonyme appelle endpoint dashboard | 401/403, aucune PII exposée |
| T14 | Credential machine incorrect | 401/403, aucun traitement accepté |
| T15 | Rejeu webhook / event_id | Effet unique, idempotence |
| T16 | Incident n8n/LLM temporaire | Etat visible, reprise ou alerte contrôlée |
| T17 | Prospect avec prompt injection dans message | Ignore les instructions du prospect, sortie bornée au schéma |
| T18 | Affichage mobile + clavier | Navigation, formulaire et validation accessibles |
| T19 | `CRM_PROVIDER=mock`, `LLM_PROVIDER=mock` | Démo totalement exécutable sans clés externes |
| T20 | Build / lint / tests | Pas d'erreurs bloquantes |

## Jeux de données recommandés

Créer 30 à 50 prospects fictifs annotés : 10 à forte intention, 10 à intention intermédiaire, 10 incomplets ou ambigus, 5 multilingues, 5 adversariaux/non pertinents. Garder les annotations hors du prompt du modèle.

## Mesures

Pour chaque suite, conserver date, version du prompt, version scoring, modèle, nombre d'échantillons et métriques avec dénominateur. Pas de « 95% de précision » annoncé sans calcul sur le jeu de test.

## Definition of done

- README complet, `.env.example`, installation reproductible.
- API, dashboard, workflows et base cohérents.
- Tests T01 à T20 automatisés ou vérifiés manuellement et documentés selon ce qui est applicable.
- Pas de credentials commitées, pas d'intégrations réelles en mode démo public.
- Tableau de bord n'affiche que des données réellement issues de la base.
- Captures et vidéo réalistes, avec labels DEMO.
