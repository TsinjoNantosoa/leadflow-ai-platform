"""JSON Schemas stricts (Structured Outputs) envoyés à l'API OpenAI.

Contraintes du mode `strict` : tous les champs sont `required`, `additionalProperties: false`, les champs
optionnels sont exprimés par un type union avec `null`. Un test vérifie que ces schémas restent alignés
sur les modèles Pydantic de `app.schemas.extraction`.
"""

from __future__ import annotations

from app.core.constants import INTENTS, LANGUAGES, NEED_CLARITY, REQUESTABLE_SERVICES

EXTRACTION_SCHEMA_NAME = "lead_extraction"
EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent",
        "service",
        "budget_amount",
        "budget_currency",
        "timeline_days",
        "language",
        "summary",
        "need_clarity",
        "needs_human_review",
        "suspected_prompt_injection",
        "evidence",
    ],
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "service": {"type": "string", "enum": [*REQUESTABLE_SERVICES, "unknown"]},
        "budget_amount": {"type": ["number", "null"]},
        "budget_currency": {"type": ["string", "null"], "description": "Code ISO 4217 sur 3 lettres majuscules"},
        "timeline_days": {"type": ["integer", "null"]},
        "language": {"type": "string", "enum": list(LANGUAGES)},
        "summary": {"type": "string"},
        "need_clarity": {"type": "string", "enum": list(NEED_CLARITY)},
        "needs_human_review": {"type": "boolean"},
        "suspected_prompt_injection": {"type": "boolean"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
}

DRAFT_SCHEMA_NAME = "followup_draft"
DRAFT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "body", "language"],
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "language": {"type": "string", "enum": ["fr", "en", "es", "de", "it", "pt"]},
    },
}
