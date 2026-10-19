from __future__ import annotations

from pydantic import ValidationError

from app.integrations.llm.base import ExtractionRequest, LlmCallResult, LlmInvalidOutput
from app.integrations.openai.client import OpenAIStructuredClient
from app.integrations.openai.prompts import EXTRACTION_PROMPT_VERSION, EXTRACTION_SYSTEM, build_extraction_input
from app.integrations.openai.schemas import EXTRACTION_SCHEMA, EXTRACTION_SCHEMA_NAME
from app.schemas.extraction import LeadExtraction


def extract_lead(client: OpenAIStructuredClient, req: ExtractionRequest, max_output_tokens: int) -> LlmCallResult[LeadExtraction]:
    result = client.structured_call(
        instructions=EXTRACTION_SYSTEM,
        user_input=build_extraction_input(req.message, req.requested_service),
        schema_name=EXTRACTION_SCHEMA_NAME,
        schema=EXTRACTION_SCHEMA,
        max_output_tokens=max_output_tokens,
    )
    try:
        output = LeadExtraction.model_validate(result.data)
    except ValidationError as exc:
        # On ne journalise pas les valeurs (elles peuvent reprendre le texte du prospect).
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise LlmInvalidOutput(f"Sortie non conforme au schéma : {', '.join(fields)}") from exc
    return LlmCallResult(
        output, "openai", result.model, EXTRACTION_PROMPT_VERSION, result.usage, result.latency_ms, result.attempts
    )
