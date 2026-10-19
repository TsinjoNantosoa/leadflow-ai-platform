from __future__ import annotations

from pydantic import ValidationError

from app.integrations.llm.base import DraftRequest, LlmCallResult, LlmInvalidOutput
from app.integrations.openai.client import OpenAIStructuredClient
from app.integrations.openai.prompts import DRAFT_PROMPT_VERSION, DRAFT_SYSTEM, build_draft_input
from app.integrations.openai.schemas import DRAFT_SCHEMA, DRAFT_SCHEMA_NAME
from app.schemas.extraction import DraftOutput


def generate_draft(client: OpenAIStructuredClient, req: DraftRequest, max_output_tokens: int) -> LlmCallResult[DraftOutput]:
    # Minimisation : prénom, société, besoin résumé et faits déclarés. Ni e-mail, ni message brut.
    context = {
        "prospect_first_name": req.first_name,
        "prospect_company": req.company,
        "language": req.language,
        "service": req.service_label,
        "need_summary": req.summary,
        "prospect_quotes": req.evidence,
        "budget_mentioned_by_prospect": (
            None if req.budget_amount is None else {"amount": req.budget_amount, "currency": req.budget_currency}
        ),
        "timeline_days_mentioned_by_prospect": req.timeline_days,
    }
    result = client.structured_call(
        instructions=DRAFT_SYSTEM,
        user_input=build_draft_input(context),
        schema_name=DRAFT_SCHEMA_NAME,
        schema=DRAFT_SCHEMA,
        max_output_tokens=max_output_tokens,
    )
    try:
        output = DraftOutput.model_validate(result.data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise LlmInvalidOutput(f"Brouillon non conforme au schéma : {', '.join(fields)}") from exc
    return LlmCallResult(
        output, "openai", result.model, DRAFT_PROMPT_VERSION, result.usage, result.latency_ms, result.attempts
    )
