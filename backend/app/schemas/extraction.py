"""Contrats de sortie du LLM. Toute sortie est re-validée ici, quel que soit le fournisseur."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import INTENTS, LANGUAGES, NEED_CLARITY, REQUESTABLE_SERVICES

IntentT = Literal[INTENTS]  # type: ignore[valid-type]
ServiceT = Literal[(*REQUESTABLE_SERVICES, "unknown")]  # type: ignore[valid-type]
ClarityT = Literal[NEED_CLARITY]  # type: ignore[valid-type]
LanguageT = Literal[LANGUAGES]  # type: ignore[valid-type]

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class LeadExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intent: IntentT
    service: ServiceT
    budget_amount: float | None = Field(None, ge=0, le=1_000_000_000)
    budget_currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    timeline_days: int | None = Field(None, ge=0, le=3650)
    language: LanguageT
    summary: str = Field(min_length=1, max_length=400)
    need_clarity: ClarityT
    needs_human_review: bool
    suspected_prompt_injection: bool = False
    evidence: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("summary")
    @classmethod
    def _clean_summary(cls, v: str) -> str:
        return _CTRL.sub("", v)

    @field_validator("evidence")
    @classmethod
    def _clean_evidence(cls, v: list[str]) -> list[str]:
        out = []
        for item in v:
            item = _CTRL.sub("", item).strip()
            if item:
                out.append(item[:200])
        return out


class DraftOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=20, max_length=3000)
    language: Literal["fr", "en", "es", "de", "it", "pt"]

    @field_validator("subject", "body")
    @classmethod
    def _clean(cls, v: str) -> str:
        return _CTRL.sub("", v)
