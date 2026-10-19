"""Scoring déterministe (F06) : règles, bornes, explications, absence d'invention."""

from __future__ import annotations

import pytest

from app.schemas.extraction import LeadExtraction
from app.services.scoring import ScoringInput, compute_score, segment_for


def ex(**kw) -> LeadExtraction:
    base = dict(intent="automation", service="unknown", budget_amount=None, budget_currency=None, timeline_days=None,
                language="fr", summary="x", need_clarity="unknown", needs_human_review=False, evidence=[])
    base.update(kw)
    return LeadExtraction(**base)


def score(extraction, *, requested=None, name="Alice Martin", email="a@example.org", company="Acme"):
    return compute_score(ScoringInput(name, email, company, requested, extraction))


def factor(res, fid):
    return next(f for f in res.factors if f["id"] == fid)


def test_perfect_lead_scores_100_hot():
    r = score(ex(service="customer_support_automation", budget_amount=3000, budget_currency="EUR", timeline_days=30,
                 need_clarity="clear"))
    assert r.score == 100 and r.segment == "HOT"
    assert sum(f["points"] for f in r.factors) == 100
    assert r.rule_version == "scoring-v1"


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        (dict(service="workflow_automation"), 30 + 10),  # service + coordonnées
        (dict(service="workflow_automation", need_clarity="clear"), 30 + 15 + 10),
        (dict(service="workflow_automation", timeline_days=31), 30 + 10),  # 31 jours : pas d'échéance courte
        (dict(service="workflow_automation", timeline_days=30), 30 + 20 + 10),
        (dict(service="workflow_automation", budget_amount=1499, budget_currency="EUR"), 30 + 10),
        (dict(service="workflow_automation", budget_amount=1500, budget_currency="EUR"), 30 + 25 + 10),
    ],
)
def test_individual_rules(kwargs, expected):
    assert score(ex(**kwargs)).score == expected


def test_missing_budget_is_never_invented_nor_excluding():
    r = score(ex(service="web_development", need_clarity="clear", timeline_days=10))
    f = factor(r, "budget_ok")
    assert f["points"] == 0 and "aucun budget" in f["detail"]
    assert r.inputs_used["budget_amount"] is None
    assert r.score == 30 + 20 + 15 + 10  # reste HOT sans budget : aucune pénalité
    assert r.segment == "HOT"


def test_non_eur_budget_not_evaluated():
    r = score(ex(service="web_development", budget_amount=99999, budget_currency="USD"))
    assert factor(r, "budget_ok")["points"] == 0
    assert "USD" in factor(r, "budget_ok")["detail"]


def test_budget_without_catalog_service_gets_no_points():
    r = score(ex(service="other", budget_amount=99999, budget_currency="EUR"))
    assert factor(r, "budget_ok")["points"] == 0


def test_requested_service_is_fallback_when_extraction_unknown():
    r = score(ex(service="unknown"), requested="data_dashboard")
    assert factor(r, "service_known")["points"] == 30
    assert "formulaire" in factor(r, "service_known")["detail"]


def test_unknown_service_zero_points():
    assert factor(score(ex(service="other"), requested="other"), "service_known")["points"] == 0


def test_incomplete_contact_details():
    r = score(ex(service="web_development"), company=None)
    assert factor(r, "contact_complete")["points"] == 0
    assert "société" in factor(r, "contact_complete")["detail"]


@pytest.mark.parametrize("value,seg", [(0, "COLD"), (44, "COLD"), (45, "WARM"), (74, "WARM"), (75, "HOT"), (100, "HOT")])
def test_segment_thresholds(value, seg):
    assert segment_for(value) == seg


def test_score_is_deterministic_and_explainable():
    e = ex(service="ai_integration", budget_amount=5000, budget_currency="EUR", need_clarity="clear")
    a, b = score(e), score(e)
    assert a.explanation() == b.explanation()
    exp = a.explanation()
    assert {"rule_version", "total", "segment", "thresholds", "factors", "inputs_used"} <= exp.keys()
    assert all({"id", "label", "max_points", "points", "awarded", "detail"} <= f.keys() for f in exp["factors"])


def test_score_always_within_bounds():
    for clarity in ("clear", "partial", "unclear", "unknown"):
        for days in (None, 0, 30, 400):
            r = score(ex(service="ai_integration", budget_amount=10**6, budget_currency="EUR", timeline_days=days,
                         need_clarity=clarity))
            assert 0 <= r.score <= 100
