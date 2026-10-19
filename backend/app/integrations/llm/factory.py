from __future__ import annotations

from app.core.config import Settings, get_settings
from app.integrations.llm.base import (
    DraftRequest,
    ExtractionRequest,
    LlmCallResult,
    LlmProvider,
)
from app.integrations.llm.mock import MockLlmProvider
from app.schemas.extraction import DraftOutput, LeadExtraction


class OpenAIProvider:
    name = "openai"

    def __init__(self, settings: Settings, client=None):
        from app.integrations.openai.client import OpenAIStructuredClient

        self._settings = settings
        self.model = settings.openai_model
        self._client = OpenAIStructuredClient(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            backoff_base_seconds=settings.llm_backoff_base_seconds,
            max_concurrency=settings.llm_max_concurrency,
            client=client,
        )

    def extract(self, req: ExtractionRequest) -> LlmCallResult[LeadExtraction]:
        from app.integrations.openai.qualification import extract_lead

        return extract_lead(self._client, req, self._settings.llm_max_output_tokens_extraction)

    def draft(self, req: DraftRequest) -> LlmCallResult[DraftOutput]:
        from app.integrations.openai.draft_generation import generate_draft

        return generate_draft(self._client, req, self._settings.llm_max_output_tokens_draft)


_provider: LlmProvider | None = None


def get_llm_provider() -> LlmProvider:
    """Singleton par processus (le client OpenAI porte le sémaphore de concurrence)."""
    global _provider
    if _provider is None:
        s = get_settings()
        _provider = OpenAIProvider(s) if s.llm_provider == "openai" else MockLlmProvider()
    return _provider


def set_llm_provider(provider: LlmProvider | None) -> None:
    """Point d'injection pour les tests."""
    global _provider
    _provider = provider
