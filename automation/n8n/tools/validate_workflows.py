"""Validation statique des 4 workflows n8n (sans instance n8n). Code de sortie 1 au moindre écart.

Contrôles : JSON valide · 4 fichiers attendus · nom préfixé `LF-` · `active: false` · connexions vers des nœuds existants ·
noms de nœuds uniques · aucun nœud d'envoi d'e-mail · aucun retryOnFail (le backend est l'unique autorité des retries) ·
aucun secret (motifs de clés, en-têtes Authorization en dur) · chemins de webhook préfixés `lf-` et uniques ·
credentials uniquement parmi les 3 placeholders `LF - …` · aucun `$env` (bloqué sur n8n 2.x).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ["WF-01-Lead-Qualification.json", "WF-02-HubSpot-CRM-Sync.json", "WF-03-Followup-Draft.json", "WF-04-Operations-Recovery.json"]
ALLOWED_CREDS = {"LF - LeadFlow API Service Token", "LF - n8n Webhook Secret", "LF - HubSpot Private App Token"}
MAIL_TYPES = re.compile(r"emailSend|gmail|smtp|sendgrid|mailgun|outlook|microsoftOutlook|mailchimp|postmark", re.I)
SECRET_PATTERNS = [re.compile(p) for p in (r"sk-[A-Za-z0-9_-]{20,}", r"pat-(na|eu)\d-[0-9a-f-]{20,}", r"Bearer\s+[A-Za-z0-9._-]{20,}")]


def check(path: Path) -> list[str]:
    errs: list[str] = []
    raw = path.read_text(encoding="utf-8")
    try:
        wf = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"JSON invalide : {exc}"]
    if not str(wf.get("name", "")).startswith("LF-"):
        errs.append("nom sans préfixe LF-")
    if wf.get("active") is not False:
        errs.append("`active` doit valoir false")
    nodes = wf.get("nodes", [])
    names = [n.get("name") for n in nodes]
    if len(names) != len(set(names)):
        errs.append("noms de nœuds dupliqués")
    for src, outs in wf.get("connections", {}).items():
        if src not in names:
            errs.append(f"connexion depuis un nœud inconnu : {src}")
        for branch in outs.get("main", []):
            for link in branch or []:
                if link["node"] not in names:
                    errs.append(f"connexion vers un nœud inconnu : {link['node']}")
    hooks = []
    for n in nodes:
        t = n.get("type", "")
        if MAIL_TYPES.search(t):
            errs.append(f"nœud d'envoi d'e-mail interdit : {n['name']} ({t})")
        if n.get("retryOnFail"):
            errs.append(f"retryOnFail interdit (retries gérés par le backend) : {n['name']}")
        if t.endswith(".webhook"):
            p = n.get("parameters", {}).get("path", "")
            hooks.append(p)
            if not p.startswith("lf-"):
                errs.append(f"chemin de webhook non préfixé lf- : {p}")
            if n.get("parameters", {}).get("authentication") != "headerAuth":
                errs.append(f"webhook sans authentification : {n['name']}")
        for cred in (n.get("credentials") or {}).values():
            if cred.get("name") not in ALLOWED_CREDS:
                errs.append(f"credential non prévu : {cred.get('name')}")
    if len(hooks) != len(set(hooks)):
        errs.append("chemins de webhook dupliqués")
    for pat in SECRET_PATTERNS:
        if pat.search(raw):
            errs.append(f"secret potentiel (motif {pat.pattern})")
    if "$env" in raw:
        errs.append("usage de $env (bloqué sur n8n 2.x)")
    return errs


def main() -> int:
    bad = 0
    for name in EXPECTED:
        p = ROOT / name
        errs = check(p) if p.exists() else ["fichier absent"]
        print(f"{'OK ' if not errs else 'KO '} {name}")
        for e in errs:
            print(f"    - {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
