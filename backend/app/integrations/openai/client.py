"""Client OpenAI (API Responses + Structured Outputs stricts) : timeouts, retries bornés, concurrence limitée.

Aucune clé n'est journalisée ni incluse dans les exceptions. `store=False` : les réponses ne sont pas
conservées côté OpenAI.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Any

import openai
from openai import OpenAI

from app.integrations.llm.base import (
    LlmConfigError,
    LlmError,
    LlmInvalidOutput,
    LlmRefusal,
    LlmTransientError,
    Usage,
)

log = logging.getLogger("leadflow.openai")


@dataclass
class StructuredResult:
    data: dict[str, Any]
    usage: Usage
    model: str
    attempts: int
    latency_ms: int


class OpenAIStructuredClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 1.0,
        max_concurrency: int = 4,
        client: OpenAI | None = None,
        sleep=time.sleep,
    ):
        self.model = model
        self.max_retries = max_retries
        self.backoff_base = backoff_base_seconds
        self._sleep = sleep
        # max_retries=0 côté SDK : la politique de reprise est la nôtre (comptée et bornée).
        self._client = client or OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)
        self._gate = threading.BoundedSemaphore(max_concurrency)

    # ------------------------------------------------------------------------------------------
    def structured_call(
        self,
        *,
        instructions: str,
        user_input: str,
        schema_name: str,
        schema: dict,
        max_output_tokens: int,
    ) -> StructuredResult:
        started = time.perf_counter()
        attempt = 0
        last_exc: LlmError | None = None
        while attempt <= self.max_retries:
            attempt += 1
            try:
                with self._gate:
                    response = self._client.responses.create(
                        model=self.model,
                        instructions=instructions,
                        input=[{"role": "user", "content": user_input}],
                        text={
                            "format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}
                        },
                        max_output_tokens=max_output_tokens,
                        store=False,
                    )
                data, usage = self._parse(response)
                return StructuredResult(
                    data=data,
                    usage=usage,
                    model=getattr(response, "model", None) or self.model,
                    attempts=attempt,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except LlmError as exc:  # refus, sortie invalide : jamais réessayés
                if not exc.retryable:
                    raise
                last_exc = exc
            except Exception as exc:  # noqa: BLE001 - mappé ci-dessous
                mapped = self._map_exception(exc)
                if not mapped.retryable:
                    raise mapped from exc
                last_exc = mapped
            if attempt <= self.max_retries:
                delay = self.backoff_base * (2 ** (attempt - 1)) * (1 + random.random() * 0.25)  # noqa: S311 - jitter, pas de crypto
                log.warning("openai_retry", extra={"attempt": attempt, "error_code": getattr(last_exc, "code", None)})
                self._sleep(delay)
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------------------------------
    @staticmethod
    def _parse(response: Any) -> tuple[dict[str, Any], Usage]:
        status = getattr(response, "status", None)
        if status == "incomplete":
            raise LlmInvalidOutput("Réponse tronquée (max_output_tokens atteint)")
        if status == "failed":
            raise LlmTransientError("Réponse en échec côté fournisseur", code="LLM_PROVIDER_FAILED")
        texts: list[str] = []
        for item in getattr(response, "output", None) or []:
            if getattr(item, "type", None) != "message":
                continue
            for part in getattr(item, "content", None) or []:
                ptype = getattr(part, "type", None)
                if ptype == "refusal":
                    raise LlmRefusal("Le modèle a refusé de répondre")
                if ptype == "output_text":
                    texts.append(getattr(part, "text", "") or "")
        raw = "".join(texts).strip()
        if not raw:
            raise LlmInvalidOutput("Réponse vide")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LlmInvalidOutput("JSON invalide") from exc
        if not isinstance(data, dict):
            raise LlmInvalidOutput("La racine du JSON n'est pas un objet")
        u = getattr(response, "usage", None)
        usage = Usage(getattr(u, "input_tokens", None), getattr(u, "output_tokens", None)) if u else Usage()
        return data, usage

    @staticmethod
    def _map_exception(exc: Exception) -> LlmError:
        if isinstance(exc, openai.APITimeoutError):
            return LlmTransientError("Timeout OpenAI", code="LLM_TIMEOUT")
        if isinstance(exc, openai.APIConnectionError):
            return LlmTransientError("Connexion OpenAI impossible", code="LLM_NETWORK")
        if isinstance(exc, openai.RateLimitError):
            body = getattr(exc, "body", None)
            code = (body.get("code") if isinstance(body, dict) else None) or getattr(exc, "code", None)
            if code == "insufficient_quota":
                return LlmConfigError("Quota OpenAI épuisé", code="LLM_QUOTA_EXHAUSTED")
            return LlmTransientError("Limite de débit OpenAI (429)", code="LLM_RATE_LIMITED")
        if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return LlmConfigError("Clé OpenAI refusée (401/403)", code="LLM_AUTH_ERROR")
        if isinstance(exc, openai.NotFoundError):
            return LlmConfigError("Modèle OpenAI introuvable ou inaccessible", code="LLM_MODEL_UNAVAILABLE")
        if isinstance(exc, openai.BadRequestError):
            return LlmConfigError("Requête OpenAI refusée (400)", code="LLM_BAD_REQUEST")
        if isinstance(exc, openai.APIStatusError):
            status = getattr(exc, "status_code", 0)
            if status >= 500 or status in (408, 409):
                return LlmTransientError(f"Erreur OpenAI {status}", code="LLM_PROVIDER_ERROR")
            return LlmConfigError(f"Erreur OpenAI {status}", code="LLM_BAD_REQUEST")
        return LlmTransientError(f"Erreur inattendue ({type(exc).__name__})", code="LLM_UNEXPECTED")
