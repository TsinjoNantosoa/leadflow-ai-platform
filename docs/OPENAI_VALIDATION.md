# Validation de l'intégration OpenAI (V1.1)

**Aucun appel réel à l'API OpenAI n'a été effectué.** Résultats mock/simulés et réels sont séparés ci-dessous.

## A. Revue du code (`backend/app/integrations/openai/`)

| Point | Constat |
| --- | --- |
| Client | SDK officiel `openai`, `max_retries=0` côté SDK ; reprises **bornées et comptées** par notre code (backoff exponentiel + jitter), sémaphore de concurrence, plafond quotidien (`LLM_DAILY_CALL_LIMIT`) |
| API | Responses API, `text.format` = `json_schema` **strict**, `store=False` |
| Schémas | Pydantic (`LeadExtraction`, `DraftOutput`) ; sortie revalidée côté backend ; JSON invalide → `LlmInvalidOutput` → revue humaine (pas de crash) |
| Refus du modèle | `LlmRefusal` → revue manuelle |
| Erreurs réseau / 429 / 5xx | retryables ; 4xx d'authentification non retryables (dead-letter) |
| Tokens | plafonds configurables (`LLM_MAX_OUTPUT_TOKENS_*`), usage dans `llm_usage` ; coût estimé **uniquement** si les tarifs sont configurés |
| Traçabilité | modèle, version de prompt, tokens enregistrés par appel |
| Anti-invention | citations vérifiées **mot à mot** dans le message ; budget absent du message → `null` ; score déterministe côté serveur |
| Injection de prompt | message traité comme donnée, heuristique → revue humaine, pas de brouillon |
| Brouillons | langue du prospect, politique `draft_policy` (aucun prix / délai / engagement / lien / e-mail inventé), modification + historique, statut `DRAFT` — aucun envoi possible |

## B. Modèle
Configurable : `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL` (défaut documenté `gpt-4.1-mini` ; jamais le placeholder `gpt-6-luna`).

**Disponibilité non confirmée.** La recherche web de cette session n'a pas atteint la documentation officielle OpenAI. Elle indique seulement que GPT‑4.1 mini a quitté *ChatGPT* le 13 février 2026 avec « aucun changement dans l'API pour le moment », et qu'Azure planifie un retrait de sa propre version. Le modèle n'a **pas** été remplacé (ni par un modèle plus coûteux). Avant usage, le smoke test commence par `models.retrieve` (gratuit) et indique si le modèle est accessible à votre clé ; sinon, choisissez un modèle listé sur la page officielle des modèles / dépréciations d'OpenAI.

## C. Résultats mock / simulés (exécutés)
- `test_openai_client.py` : 33 tests du client contre le **vrai SDK** avec transport httpx simulé (succès, JSON invalide, refus, 429 avec `Retry-After`, 5xx, timeout, 401, plafonds, concurrence).
- `test_pipeline.py`, E2E Playwright, n8n local : pipeline complet avec `LLM_PROVIDER=mock`.
- Limite : le mock imite le **contrat**, pas l'intelligence du modèle. Aucune mesure de qualité d'extraction n'est revendiquée.

## D. Résultats réels
**Aucun.** `tests/test_openai_live.py` (2 tests) est ignoré sans activation.

## E. Smoke test optionnel (à lancer par vous)
```bash
cd backend
OPENAI_SMOKE_ENABLE=1 OPENAI_API_KEY=... OPENAI_MODEL=gpt-4.1-mini python -m scripts.openai_smoke --max-calls 2
```
Garde-fous : refus sans `OPENAI_SMOKE_ENABLE=1` (code 3) ; clé / modèle requis (code 2) ; vérification gratuite du modèle d'abord (code 1 si inaccessible, **aucun appel payant**) ; données fictives ; 2 appels par défaut, plafond dur 4 ; sorties ≤ 400 tokens ; clé jamais affichée. Contrôles : budget 3000 extrait, injection détectée, citations présentes, brouillon conforme à la politique. Fixez aussi une limite de dépense côté compte OpenAI.
