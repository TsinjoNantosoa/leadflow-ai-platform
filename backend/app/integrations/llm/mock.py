"""Fournisseur LLM déterministe, sans réseau ni clé (LLM_PROVIDER=mock).

Il imite le CONTRAT du fournisseur réel, pas son intelligence : heuristiques simples à base de mots-clés.
Des balises de test `[[mock:...]]` dans le message permettent de simuler les pannes en démo et en tests
(uniquement avec ce fournisseur ; elles n'ont aucun effet avec OpenAI).
"""

from __future__ import annotations

import re
import time

from app.core.constants import SERVICE_CATALOG
from app.integrations.llm.base import (
    DraftRequest,
    ExtractionRequest,
    LlmCallResult,
    LlmInvalidOutput,
    LlmRefusal,
    LlmTransientError,
    Usage,
)
from app.schemas.extraction import DraftOutput, LeadExtraction

PROMPT_VERSION = "mock-v1"

_KEYWORDS: list[tuple[str, str, str]] = [
    # (regex, service, intent)
    (r"support client|service client|demandes? clients?|customer support|helpdesk|atenci[oó]n al cliente|tickets?", "customer_support_automation", "automation"),
    (r"chatbot|agent ia|ia\b|intelligence artificielle|\bai\b|llm|openai|inteligencia artificial", "ai_integration", "ai_solution"),
    (r"dashboard|tableau de bord|reporting|bi\b|donn[ée]es|data", "data_dashboard", "data_analytics"),
    (r"site (web|vitrine|e-?commerce)|website|refonte|landing|boutique en ligne|sitio web", "web_development", "web_development"),
    (r"automatis|workflow|n8n|zapier|int[eé]gration|crm|process|automatiz", "workflow_automation", "automation"),
]

_FR = {"bonjour", "nous", "notre", "besoin", "souhaitons", "voulons", "mois", "pour", "une", "des", "avec", "est"}
_EN = {"hello", "we", "our", "need", "would", "like", "month", "for", "the", "with", "and", "want"}
_ES = {"hola", "necesitamos", "nuestro", "queremos", "para", "una", "con", "mes", "somos"}
_DE = {"hallo", "wir", "unser", "brauchen", "möchten", "für", "und", "monat", "ein"}


def detect_language(text: str) -> str:
    words = set(re.findall(r"[a-zà-ÿ']+", text.lower()))
    scores = {"fr": len(words & _FR), "en": len(words & _EN), "es": len(words & _ES), "de": len(words & _DE)}
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] >= 2 else ("unknown" if not words else "other")


_BUDGET_RE = re.compile(
    r"(?P<num>\d{1,3}(?:[ .  ]\d{3})+|\d+(?:[.,]\d+)?)\s*(?P<k>k)?\s*(?P<cur>€|eur(?:os?)?|usd|\$|dollars?|gbp|£)?",
    re.IGNORECASE,
)


def _parse_budget(text: str) -> tuple[float | None, str | None]:
    for m in _BUDGET_RE.finditer(text):
        cur = (m.group("cur") or "").lower()
        if not cur:
            continue
        raw = m.group("num")
        raw = re.sub(r"[ .  ](?=\d{3}\b)", "", raw).replace(",", ".")
        try:
            amount = float(raw)
        except ValueError:
            continue
        if m.group("k"):
            amount *= 1000
        code = {"€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "usd": "USD", "$": "USD", "dollar": "USD",
                "dollars": "USD", "gbp": "GBP", "£": "GBP"}.get(cur, "EUR")
        return amount, code
    return None, None


_TIMELINE_RE = [
    (re.compile(r"(\d+)\s*(?:jours?|days?|d[ií]as)", re.I), 1),
    (re.compile(r"(\d+)\s*(?:semaines?|weeks?|semanas?)", re.I), 7),
    (re.compile(r"(\d+)\s*(?:mois|months?|meses)", re.I), 30),
]


def _parse_timeline(text: str) -> int | None:
    t = text.lower()
    for rx, mult in _TIMELINE_RE:
        m = rx.search(t)
        if m:
            return int(m.group(1)) * mult
    if re.search(r"\b(un|1|one|un) (mois|month|mes)\b|dans un mois|within a month|next month|le mois prochain", t):
        return 30
    if re.search(r"\b(asap|urgent|imm[ée]diatement|d[eè]s que possible|tout de suite)\b", t):
        return 14
    return None


def _first_sentence_with(text: str, pattern: str) -> str | None:
    for sent in re.split(r"(?<=[.!?\n])\s+", text):
        if re.search(pattern, sent, re.I):
            return sent.strip()[:200]
    return None


class MockLlmProvider:
    name = "mock"
    model = "mock-heuristic-1"

    def extract(self, req: ExtractionRequest) -> LlmCallResult[LeadExtraction]:
        start = time.perf_counter()
        msg = req.message
        low = msg.lower()
        if "[[mock:refusal]]" in low:
            raise LlmRefusal("Refus simulé par le mock")
        if "[[mock:invalid]]" in low:
            raise LlmInvalidOutput("Sortie JSON invalide simulée par le mock")
        if "[[mock:timeout]]" in low:
            raise LlmTransientError("Timeout simulé par le mock", code="LLM_TIMEOUT")

        service, intent = "unknown", "unknown"
        for rx, svc, itt in _KEYWORDS:
            if re.search(rx, low):
                service, intent = svc, itt
                break
        if service == "unknown" and req.requested_service in SERVICE_CATALOG:
            service = req.requested_service  # type: ignore[assignment]
            intent = {"web_development": "web_development", "ai_integration": "ai_solution",
                      "data_dashboard": "data_analytics"}.get(service, "automation")
        elif service == "unknown" and req.requested_service == "other":
            service, intent = "other", "other"

        amount, currency = _parse_budget(msg)
        timeline = _parse_timeline(msg)
        word_count = len(re.findall(r"\w+", msg))
        has_need_verb = bool(re.search(r"automatis|besoin|souhait|voulons|cherchons|need|want|looking|necesit|brauch|refonte|cr[eé]er|mettre en place", low))
        clarity = "clear" if (has_need_verb and word_count >= 12 and service != "unknown") else (
            "partial" if has_need_verb or service != "unknown" else "unclear")
        evidence = [e for e in [
            _first_sentence_with(msg, r"automatis|besoin|souhait|voulons|cherchons|need|want|looking|necesit|brauch|refonte|site|chatbot|dashboard")
        ] if e]
        injected = bool(re.search(r"ignore (all |previous|the )|ignore[zr]? (les|toutes)|system prompt|score (to|à) 100", low))
        language = detect_language(msg)
        needs_review = injected or clarity == "unclear" or language == "unknown"

        out = LeadExtraction(
            intent=intent,  # type: ignore[arg-type]
            service=service,  # type: ignore[arg-type]
            budget_amount=amount,
            budget_currency=currency,
            timeline_days=timeline,
            language=language,  # type: ignore[arg-type]
            summary=_summary(service, amount, currency, timeline),
            need_clarity=clarity,  # type: ignore[arg-type]
            needs_human_review=needs_review,
            suspected_prompt_injection=injected,
            evidence=evidence,
        )
        return LlmCallResult(out, "mock", self.model, PROMPT_VERSION, Usage(0, 0), int((time.perf_counter() - start) * 1000))

    def draft(self, req: DraftRequest) -> LlmCallResult[DraftOutput]:
        start = time.perf_counter()
        lang = req.language if req.language in ("fr", "en", "es", "de", "it", "pt") else "fr"
        label = req.service_label
        if lang == "en":
            subject = f"Your request – {label}"
            body = (
                f"Hello {req.first_name},\n\n"
                f"Thank you for contacting NovaDigital about {label.lower()}. "
                f"We understood the following: {req.summary}\n\n"
                "We would be glad to schedule a short call to clarify your needs and discuss possible next steps.\n"
                "Could you let us know which times suit you best?\n\n"
                "Kind regards,\nThe NovaDigital team"
            )
            lang_out = "en"
        else:
            subject = f"Votre demande – {label}"
            body = (
                f"Bonjour {req.first_name},\n\n"
                f"Merci d'avoir contacté NovaDigital au sujet de : {label.lower()}. "
                f"Voici ce que nous avons compris : {req.summary}\n\n"
                "Nous serions heureux d'organiser un court échange afin de préciser vos besoins "
                "et d'envisager les prochaines étapes.\n"
                "Pouvez-vous nous indiquer vos disponibilités ?\n\n"
                "Cordialement,\nL'équipe NovaDigital"
            )
            lang_out = "fr"
        out = DraftOutput(subject=subject, body=body, language=lang_out)  # type: ignore[arg-type]
        return LlmCallResult(out, "mock", self.model, PROMPT_VERSION, Usage(0, 0), int((time.perf_counter() - start) * 1000))


def _summary(service: str, amount: float | None, currency: str | None, timeline: int | None) -> str:
    label = SERVICE_CATALOG[service].label_fr if service in SERVICE_CATALOG else "Demande commerciale"
    parts = [label]
    if amount is not None:
        parts.append(f"budget indicatif {amount:g} {currency or ''}".strip())
    if timeline is not None:
        parts.append(f"échéance ~{timeline} jours")
    return " – ".join(parts)[:400]
