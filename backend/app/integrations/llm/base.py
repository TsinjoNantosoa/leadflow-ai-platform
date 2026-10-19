"""Interface commune des fournisseurs LLM (mock / OpenAI) et exceptions typées."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from app.schemas.extraction import DraftOutput, LeadExtraction

T = TypeVar("T")


class LlmError(Exception):
    """Base. `code` est stable et exposé dans l'API ; `retryable` pilote la reprise par l'outbox."""

    code = "LLM_ERROR"
    retryable = False

    def __init__(self, message: str = "", *, code: str | None = None):
        super().__init__(message or self.code)
        if code:
            self.code = code


class LlmRefusal(LlmError):
    code = "LLM_REFUSAL"


class LlmInvalidOutput(LlmError):
    code = "LLM_INVALID_OUTPUT"


class LlmTransientError(LlmError):
    """Timeout, 429, 5xx, réseau : réessayer plus tard a un sens."""

    code = "LLM_UNAVAILABLE"
    retryable = True


class LlmConfigError(LlmError):
    """Clé invalide, modèle inaccessible, quota épuisé : inutile de réessayer sans intervention."""

    code = "LLM_CONFIG_ERROR"


class LlmBudgetExceeded(LlmError):
    code = "LLM_DAILY_LIMIT"
    retryable = True


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass
class LlmCallResult(Generic[T]):
    output: T
    provider: str
    model: str
    prompt_version: str
    usage: Usage
    latency_ms: int
    attempts: int = 1


@dataclass(frozen=True)
class ExtractionRequest:
    message: str  # donnée NON fiable
    requested_service: str | None


@dataclass(frozen=True)
class DraftRequest:
    first_name: str
    company: str | None
    language: str  # langue du prospect (fr/en/...)
    service_id: str | None
    service_label: str
    summary: str
    evidence: list[str]
    budget_amount: float | None
    budget_currency: str | None
    timeline_days: int | None


class LlmProvider(Protocol):
    name: str
    model: str

    def extract(self, req: ExtractionRequest) -> LlmCallResult[LeadExtraction]: ...

    def draft(self, req: DraftRequest) -> LlmCallResult[DraftOutput]: ...
