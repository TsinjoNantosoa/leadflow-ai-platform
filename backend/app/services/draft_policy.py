"""Contrôle de politique d'un brouillon : pas de prix/engagement inventés, pas de lien, pas de placeholder."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_URL = re.compile(r"(https?://|www\.)\S+|\b[\w.-]+\.(com|fr|io|net|org|ai|co)\b/\S*", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PLACEHOLDER = re.compile(r"\[[^\]\n]{1,40}\]|\{\{?[^}\n]{1,40}\}?\}|<[A-Za-z ]{1,30}>")
_MONEY = re.compile(
    r"(?:(?:€|\$|£)\s?\d[\d\s.,]*|\d[\d\s.,]*\s?(?:€|\$|£|eur(?:os?)?\b|usd\b|k€|k\s?eur\b|dollars?\b))", re.I
)
_PERCENT = re.compile(r"\d+\s?%")
_COMMITMENTS = re.compile(
    r"\b(garanti\w*|garantis\w*|guarantee\w*|je vous promets|nous promettons|we promise|promise[sd]?|"
    r"sans engagement de (?:notre|votre) part|gratuit(?:ement)?|free of charge|remise|discount|tarif de|prix de|"
    r"livr[ée]s? (?:en|sous|avant)|livraison (?:en|sous|avant)|delivered (?:in|within|by)|d[ée]lai de \d+|"
    r"dans (?:un|une|\d+) (?:semaines?|mois|jours?)|within \d+ (?:days|weeks|months))\b",
    re.I,
)


@dataclass
class PolicyResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def check_draft_policy(subject: str, body: str, *, allowed_budget: float | None = None) -> PolicyResult:
    text = f"{subject}\n{body}"
    violations: list[str] = []

    if _URL.search(text):
        violations.append("contains_link")
    if _EMAIL.search(text):
        violations.append("contains_email_address")
    if _PLACEHOLDER.search(text):
        violations.append("contains_placeholder")
    if _COMMITMENTS.search(text):
        violations.append("commitment_or_delay")
    if _PERCENT.search(text):
        violations.append("contains_percentage")

    for m in _MONEY.finditer(text):
        digits = re.sub(r"[^\d]", "", m.group(0))
        if allowed_budget is not None and digits and int(digits) == int(allowed_budget):
            continue  # reprise du budget cité par le prospect lui-même
        violations.append("invented_price")
        break

    return PolicyResult(ok=not violations, violations=sorted(set(violations)))
