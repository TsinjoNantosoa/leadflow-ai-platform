"""Scoring déterministe et explicable (aucun LLM). Fonction pure : mêmes entrées => même score."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.constants import (
    HOT_THRESHOLD,
    SCORING_RULE_VERSION,
    SERVICE_CATALOG,
    SHORT_TIMELINE_DAYS,
    WARM_THRESHOLD,
    Segment,
)
from app.schemas.extraction import LeadExtraction

POINTS = {
    "service_known": 30,
    "budget_ok": 25,
    "short_timeline": 20,
    "explicit_need": 15,
    "contact_complete": 10,
}
LABELS = {
    "service_known": "Service du catalogue",
    "budget_ok": "Budget conforme au minimum du service",
    "short_timeline": f"Échéance courte (<= {SHORT_TIMELINE_DAYS} jours)",
    "explicit_need": "Besoin explicite",
    "contact_complete": "Coordonnées complètes",
}


@dataclass(frozen=True)
class ScoringInput:
    full_name: str
    email: str
    company: str | None
    requested_service: str | None
    extraction: LeadExtraction


@dataclass
class ScoreResult:
    score: int
    segment: str
    rule_version: str
    factors: list[dict[str, Any]] = field(default_factory=list)
    inputs_used: dict[str, Any] = field(default_factory=dict)

    def explanation(self) -> dict[str, Any]:
        return {
            "rule_version": self.rule_version,
            "total": self.score,
            "segment": self.segment,
            "thresholds": {"HOT": HOT_THRESHOLD, "WARM": WARM_THRESHOLD},
            "factors": self.factors,
            "inputs_used": self.inputs_used,
        }


def segment_for(score: int) -> str:
    if score >= HOT_THRESHOLD:
        return Segment.HOT.value
    if score >= WARM_THRESHOLD:
        return Segment.WARM.value
    return Segment.COLD.value


def _factor(fid: str, awarded: bool, detail: str) -> dict[str, Any]:
    return {
        "id": fid,
        "label": LABELS[fid],
        "max_points": POINTS[fid],
        "points": POINTS[fid] if awarded else 0,
        "awarded": awarded,
        "detail": detail,
    }


def resolve_service(requested: str | None, extracted: str | None) -> tuple[str | None, str]:
    """Service retenu pour le scoring : celui extrait s'il est au catalogue, sinon celui déclaré par le prospect."""
    if extracted in SERVICE_CATALOG:
        return extracted, "extrait du message"
    if requested in SERVICE_CATALOG:
        return requested, "déclaré dans le formulaire"
    return None, "aucun service du catalogue identifié"


def compute_score(inp: ScoringInput) -> ScoreResult:
    ex = inp.extraction
    service, service_origin = resolve_service(inp.requested_service, ex.service)
    factors: list[dict[str, Any]] = []

    # 1. Service connu
    if service:
        factors.append(_factor("service_known", True, f"{service} ({service_origin})"))
    else:
        factors.append(_factor("service_known", False, service_origin))

    # 2. Budget conforme (jamais inventé : budget absent => 0 point, sans pénalité ni exclusion)
    if ex.budget_amount is None:
        factors.append(_factor("budget_ok", False, "aucun budget mentionné"))
    elif service is None:
        factors.append(_factor("budget_ok", False, "pas de minimum applicable sans service du catalogue"))
    elif ex.budget_currency != "EUR":
        factors.append(
            _factor("budget_ok", False, f"devise {ex.budget_currency or 'non précisée'} non évaluée (minimums en EUR)")
        )
    else:
        minimum = SERVICE_CATALOG[service].min_budget_eur
        ok = ex.budget_amount >= minimum
        factors.append(
            _factor("budget_ok", ok, f"{ex.budget_amount:g} EUR {'>=' if ok else '<'} minimum {minimum} EUR pour {service}")
        )

    # 3. Échéance courte
    if ex.timeline_days is None:
        factors.append(_factor("short_timeline", False, "aucune échéance mentionnée"))
    else:
        ok = ex.timeline_days <= SHORT_TIMELINE_DAYS
        factors.append(
            _factor("short_timeline", ok, f"{ex.timeline_days} jours {'<=' if ok else '>'} {SHORT_TIMELINE_DAYS}")
        )

    # 4. Besoin explicite
    factors.append(_factor("explicit_need", ex.need_clarity == "clear", f"clarté du besoin : {ex.need_clarity}"))

    # 5. Coordonnées complètes : nom, e-mail et société renseignés
    missing = [
        label
        for label, value in (("nom", inp.full_name), ("e-mail", inp.email), ("société", inp.company))
        if not (value and value.strip())
    ]
    factors.append(_factor("contact_complete", not missing, "complètes" if not missing else f"manquant : {', '.join(missing)}"))

    score = max(0, min(100, sum(f["points"] for f in factors)))
    return ScoreResult(
        score=score,
        segment=segment_for(score),
        rule_version=SCORING_RULE_VERSION,
        factors=factors,
        inputs_used={
            "service": service,
            "service_origin": service_origin,
            "budget_amount": ex.budget_amount,
            "budget_currency": ex.budget_currency,
            "timeline_days": ex.timeline_days,
            "need_clarity": ex.need_clarity,
            "contact_fields_present": {
                "full_name": bool(inp.full_name and inp.full_name.strip()),
                "email": bool(inp.email and inp.email.strip()),
                "company": bool(inp.company and inp.company.strip()),
            },
        },
    )
