from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.llm.base import LlmBudgetExceeded, LlmCallResult, LlmError
from app.models import LlmUsage
from app.observability.logging import correlation_id_var


def check_budget(db: Session) -> None:
    limit = get_settings().llm_daily_call_limit
    if not limit:
        return
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    calls = db.execute(
        select(func.count()).select_from(LlmUsage).where(LlmUsage.created_at >= start, LlmUsage.provider != "mock")
    ).scalar_one()
    if calls >= limit:
        raise LlmBudgetExceeded("Limite quotidienne d'appels LLM atteinte")


def estimate_cost(input_tokens: int | None, output_tokens: int | None) -> Decimal | None:
    """Estimation uniquement si les tarifs sont configurés ET les tokens connus ; sinon None (jamais inventé)."""
    s = get_settings()
    if s.llm_price_input_per_mtok is None or s.llm_price_output_per_mtok is None:
        return None
    if input_tokens is None or output_tokens is None:
        return None
    cost = (input_tokens * s.llm_price_input_per_mtok + output_tokens * s.llm_price_output_per_mtok) / 1_000_000
    return Decimal(str(round(cost, 6)))


def _cid() -> uuid.UUID | None:
    try:
        v = correlation_id_var.get()
        return uuid.UUID(v) if v else None
    except ValueError:
        return None


def record_success(db: Session, *, lead_id: uuid.UUID | None, kind: str, result: LlmCallResult) -> None:
    db.add(
        LlmUsage(
            lead_id=lead_id,
            kind=kind,
            provider=result.provider,
            model=result.model,
            prompt_version=result.prompt_version,
            status="ok",
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            estimated_cost_usd=estimate_cost(result.usage.input_tokens, result.usage.output_tokens),
            latency_ms=result.latency_ms,
            correlation_id=_cid(),
        )
    )


def record_failure(db: Session, *, lead_id: uuid.UUID | None, kind: str, provider: str, model: str | None,
                   exc: LlmError) -> None:
    db.add(
        LlmUsage(lead_id=lead_id, kind=kind, provider=provider, model=model, status=exc.code, correlation_id=_cid())
    )
