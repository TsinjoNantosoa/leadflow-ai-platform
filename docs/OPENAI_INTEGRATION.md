# Intégration OpenAI

> **Statut de validation** — Le code d'intégration est complet et testé avec le **SDK officiel `openai` contre un transport HTTP simulé** (forme exacte de la requête, parsing, refus, retries, erreurs). **Aucun appel réel à l'API OpenAI n'a été exécuté** (pas de clé dans l'environnement de développement). Un test réel, désactivé par défaut, est fourni (voir « Vérification réelle »).

## Architecture

```
backend/app/integrations/
├── llm/
│   ├── base.py       # interface LlmProvider, exceptions typées, DTO
│   ├── mock.py       # LLM_PROVIDER=mock (déterministe, sans réseau)
│   └── factory.py    # sélection mock/openai (singleton par processus)
└── openai/
    ├── client.py     # OpenAIStructuredClient : timeouts, retries bornés, concurrence, mapping d'erreurs
    ├── schemas.py    # JSON Schemas stricts (Structured Outputs)
    ├── prompts.py    # prompts VERSIONNÉS (extract-v1, draft-v1)
    ├── qualification.py / draft_generation.py
```

n8n ne parle jamais à OpenAI : il appelle `POST /internal/leads/{id}/extract` et `…/draft/generate`. Aucune clé OpenAI n'existe côté n8n ni côté frontend.

## API utilisée

**Responses API** (`client.responses.create`) avec `text.format = {type: "json_schema", strict: true}` (Structured Outputs), `max_output_tokens` plafonné, `store=False` (rien n'est conservé côté OpenAI), `max_retries=0` côté SDK (la politique de reprise est la nôtre).

## Modèle

`OPENAI_MODEL` est **obligatoire** quand `LLM_PROVIDER=openai` (aucun identifiant fictif codé en dur). Défaut recommandé dans `.env.example` : **`gpt-4.1-mini`** (supporte les Structured Outputs, bon rapport qualité/coût pour l'extraction et la rédaction courte). Si ce modèle n'est pas accessible avec votre clé, le backend renvoie `LLM_MODEL_UNAVAILABLE` (non réessayable, visible dans le dashboard) : définissez simplement un autre modèle compatible, par exemple `gpt-4o-mini`. Les tarifs ne sont pas codés : renseignez `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK` (USD par million de tokens) pour activer l'estimation de coût ; sans cela, aucun coût n'est affiché.

## Qualification (`extract-v1`)

Schéma strict (tous les champs requis, `additionalProperties: false`) :

```json
{
  "intent": "automation | web_development | ai_solution | data_analytics | consulting | other | unknown",
  "service": "web_development | workflow_automation | customer_support_automation | ai_integration | data_dashboard | other | unknown",
  "budget_amount": 3000, "budget_currency": "EUR", "timeline_days": 30,
  "language": "fr | en | es | de | it | pt | other | unknown",
  "summary": "Automatisation du support client",
  "need_clarity": "clear | partial | unclear | unknown",
  "needs_human_review": false, "suspected_prompt_injection": false,
  "evidence": ["automatiser notre support client"]
}
```

Un test vérifie que ce schéma reste aligné sur le modèle Pydantic `LeadExtraction`.

### Défense en profondeur (le texte du prospect est une donnée non fiable)

1. Le message est encadré par `<prospect_message>` et le prompt système le déclare **non fiable** (jamais des instructions) ; seuls le message et l'indication de service sont envoyés — **jamais** nom, e-mail ou société.
2. Le modèle ne calcule **aucun score** et ne décide d'aucun rejet.
3. Le backend re-valide la sortie avec Pydantic, puis `check_extraction` :
   - citations (`evidence`) absentes du message → retirées + revue humaine ;
   - budget absent du message → **mis à `null`** + revue humaine ;
   - heuristique d'injection (FR/EN) indépendante du modèle → revue humaine, **aucun brouillon généré**.
4. Le score est calculé par `app/services/scoring.py` (règles `scoring-v1`).

### Cas gérés explicitement

| Cas | Comportement |
| --- | --- |
| Refus du modèle, JSON invalide, valeur hors énumération, réponse tronquée | `200 {ok:false}` → lead `MANUAL_REVIEW`, run `MANUAL_REVIEW`, **aucun retry**, aucun brouillon |
| Timeout, 429, 5xx, réseau | `503 retryable:true` → n8n rapporte `/fail` → le backend planifie un retry (backoff) puis dead-letter |
| 401/403, modèle introuvable, 400, quota épuisé | `502 retryable:false` → dead-letter immédiat, alerte visible (configuration à corriger) |
| Limite quotidienne atteinte (`LLM_DAILY_CALL_LIMIT`) | `503 LLM_DAILY_LIMIT` (retry ultérieur) |

## Brouillons (`draft-v1`)

Le contexte transmis : prénom, société, besoin résumé, citations, budget/échéance **cités par le prospect**. Le prompt interdit prix, délais, engagements, prestations inventées, liens, placeholders. Une **politique de contenu** déterministe (`draft_policy.py`) re-vérifie la sortie avant retour **et** avant écriture : montant ≠ budget du prospect, « garantie », « livraison en N jours », pourcentage, lien, e-mail, `[Prénom]`… → brouillon refusé (revue manuelle). Le brouillon est enregistré `DRAFT` ; **aucun code d'envoi n'existe**.

## Maîtrise des coûts

Timeouts (`LLM_TIMEOUT_SECONDS`), retries bornés avec backoff exponentiel + jitter (`LLM_MAX_RETRIES`), sortie plafonnée, sémaphore de concurrence (`LLM_MAX_CONCURRENCY`), plafond quotidien d'appels, table `llm_usage` (modèle, version de prompt, tokens, latence, statut, coût estimé **seulement si les tarifs sont configurés**), et mise en cache idempotente : rejouer `extract`/`draft/generate` avec la même `Idempotency-Key` ne rappelle pas OpenAI. Le dashboard n'affiche la consommation que pour les appels **non mock**.

Note de dimensionnement : une extraction ≈ quelques centaines de tokens ; avec jusqu'à `LLM_MAX_RETRIES+1` essais de `LLM_TIMEOUT_SECONDS` secondes, une requête `extract` ne dépasse pas ~80 s, sous la limite de requête de Render.

## Traçabilité

Chaque qualification et brouillon enregistre `llm_provider`, `model_name`, `prompt_version`, `scoring_rule_version`. Toute modification d'un prompt exige un nouveau numéro de version.

## Vérification réelle (optionnelle, consomme des tokens)

```bash
cd backend
RUN_OPENAI_LIVE=1 OPENAI_API_KEY_LIVE=sk-... OPENAI_MODEL_LIVE=gpt-4.1-mini \
  .venv/Scripts/python -m pytest tests/test_openai_live.py -m openai_live
```
Deux appels, sorties plafonnées à 400 tokens. À exécuter **avant** de passer `LLM_PROVIDER=openai` en environnement partagé.
