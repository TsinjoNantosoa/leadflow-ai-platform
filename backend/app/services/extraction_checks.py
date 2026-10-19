"""Contrôles déterministes appliqués à la sortie du LLM (défense contre hallucinations et injections)."""

from __future__ import annotations

import re
import unicodedata

from app.schemas.extraction import LeadExtraction

_INJECTION_PATTERNS = [
    r"ignore (all |any |the |your )?(previous|prior|above|earlier) (instructions|prompts?|rules)",
    r"disregard (all |any |the |your )?(previous|prior|above) ",
    r"(forget|override) (all |your |the )?(previous |prior )?(instructions|rules|guidelines)",
    r"ignore[zr]? (toutes? )?(les |tes |vos )?(instructions|consignes|r[eè]gles)",
    r"oublie[zr]? (toutes? )?(les |tes |vos )?(instructions|consignes|r[eè]gles)",
    r"(system|developer) (prompt|message|instructions?)",
    r"prompt syst[eè]me",
    r"you are now\b",
    r"tu es (maintenant|d[ée]sormais)\b",
    r"\bact as (a |an |the )?(?!customer|client)",
    r"(set|mets?|fixe[rz]?|donne[rz]?) (the |le |ce )?(lead )?score (to|[àa]) ?\d+",
    r"score (of |de )?100\b",
    r"(mark|classe[rz]?|classify) (this|ce) (lead|prospect) as (hot|chaud)",
    r"reveal (your|the) (prompt|instructions)",
    r"r[eé]v[eè]le (ton|le|tes) (prompt|instructions)",
    r"<\s*/?\s*(system|assistant|prospect_message)\s*>",
    r"\bjailbreak\b",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def detect_prompt_injection(text: str) -> bool:
    """Heuristique volontairement prudente : un faux positif envoie simplement le lead en revue humaine."""
    return any(rx.search(text) for rx in _INJECTION_RE)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold()
    return re.sub(r"\s+", " ", s).strip()


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def check_extraction(extraction: LeadExtraction, message: str) -> tuple[LeadExtraction, list[str]]:
    """Retourne l'extraction nettoyée et la liste des raisons de revue humaine.

    - les citations (`evidence`) absentes du message sont retirées ;
    - un budget qui ne correspond à aucun nombre du message est mis à null ;
    - une échéance sans aucun chiffre ni mot de durée n'est pas supprimée (le français écrit "un mois").
    """
    reasons: list[str] = []
    data = extraction.model_copy(deep=True)
    msg_norm = _norm(message)

    if extraction.needs_human_review:
        reasons.append("llm_flagged_review")
    if extraction.suspected_prompt_injection or detect_prompt_injection(message):
        data.suspected_prompt_injection = True
        reasons.append("prompt_injection_suspected")

    kept = [e for e in extraction.evidence if _norm(e) in msg_norm]
    if len(kept) != len(extraction.evidence):
        reasons.append("evidence_not_found_in_message")
    data.evidence = kept

    if data.budget_amount is not None:
        number = int(data.budget_amount)
        # Groupes de chiffres du message ("3 000" -> "3000"), plus la forme abrégée "3k" pour 3000.
        groups = {_digits(m) for m in re.findall(r"\d[\d\s.,  ]*\d|\d", message)}
        accepted = {str(number)} | ({str(number // 1000)} if number >= 1000 and number % 1000 == 0 else set())
        if not (groups & accepted):
            data.budget_amount = None
            data.budget_currency = None
            reasons.append("budget_not_found_in_message")
    if data.budget_amount is None:
        data.budget_currency = None

    if data.need_clarity in ("unclear", "unknown"):
        reasons.append("need_unclear")
    if not kept and data.need_clarity == "clear":
        reasons.append("clear_need_without_evidence")

    data.needs_human_review = bool(reasons)
    return data, sorted(set(reasons))
