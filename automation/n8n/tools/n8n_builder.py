"""Mini-DSL pour produire des exports n8n cohérents (IDs déterministes, connexions vérifiées).

Les fichiers JSON générés sont le livrable ; ce module n'existe que pour éviter les erreurs de câblage à la main.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

NS = uuid.UUID("0b0c9a3e-2d9f-4f0b-9e43-0c6a1f1a7e10")

# Credentials : IDs placeholders explicites, à réaffecter après import (voir IMPORT_GUIDE.md).
CRED_API = {"httpHeaderAuth": {"id": "LF_CRED_API_SERVICE_TOKEN", "name": "LF - LeadFlow API Service Token"}}
CRED_WEBHOOK_HEADER = {"httpHeaderAuth": {"id": "LF_CRED_N8N_WEBHOOK_SECRET", "name": "LF - n8n Webhook Secret"}}
CRED_HUBSPOT = {"hubspotAppToken": {"id": "LF_CRED_HUBSPOT_TOKEN", "name": "LF - HubSpot Private App Token"}}

API_PLACEHOLDER = "https://YOUR-LEADFLOW-API-HOST.example.com/api/v1/internal"
N8N_PLACEHOLDER = "http://localhost:5678"

COND_OPTS = {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2}


class Workflow:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.nodes: list[dict[str, Any]] = []
        self.connections: dict[str, dict[str, list[list[dict[str, Any]]]]] = {}
        self._names: set[str] = set()

    # -- noeuds --------------------------------------------------------------------------------------
    def node(self, name: str, type_: str, version: float, params: dict, pos: tuple[int, int], *,
             credentials: dict | None = None, on_error: str | None = None, webhook: bool = False,
             notes: str | None = None, disabled: bool = False) -> str:
        assert name not in self._names, f"nom de nœud dupliqué : {name}"
        self._names.add(name)
        node: dict[str, Any] = {
            "parameters": params,
            "id": str(uuid.uuid5(NS, f"{self.name}:{name}")),
            "name": name,
            "type": type_,
            "typeVersion": version,
            "position": list(pos),
        }
        if credentials:
            node["credentials"] = credentials
        if on_error:
            node["onError"] = on_error
        if webhook:
            node["webhookId"] = str(uuid.uuid5(NS, f"{self.name}:{name}:webhook"))
        if notes:
            node["notes"] = notes
            node["notesInFlow"] = False
        if disabled:
            node["disabled"] = True
        self.nodes.append(node)
        return name

    def connect(self, src: str, dst: str, output: int = 0) -> None:
        assert src in self._names and dst in self._names, f"connexion invalide {src} -> {dst}"
        outs = self.connections.setdefault(src, {}).setdefault("main", [])
        while len(outs) <= output:
            outs.append([])
        outs[output].append({"node": dst, "type": "main", "index": 0})

    def chain(self, *names: str) -> None:
        for a, b in zip(names, names[1:], strict=False):
            self.connect(a, b)

    # -- raccourcis ----------------------------------------------------------------------------------
    def note(self, text: str, pos: tuple[int, int], size: tuple[int, int] = (360, 200), color: int = 4) -> None:
        name = f"Note {len(self._names) + 1}"
        self.node(name, "n8n-nodes-base.stickyNote", 1,
                  {"content": text, "height": size[1], "width": size[0], "color": color}, pos)

    def set_node(self, name: str, fields: dict[str, Any], pos: tuple[int, int], keep_others: bool = False) -> str:
        assigns = []
        for key, value in fields.items():
            if isinstance(value, tuple):  # (valeur, type explicite)
                value, typ = value
            else:
                typ = "number" if isinstance(value, (int, float)) and not isinstance(value, bool) else (
                    "boolean" if isinstance(value, bool) else "string")
            assigns.append({"id": str(uuid.uuid5(NS, f"{self.name}:{name}:{key}")), "name": key, "value": value, "type": typ})
        return self.node(name, "n8n-nodes-base.set", 3.4,
                         {"assignments": {"assignments": assigns}, "includeOtherFields": keep_others, "options": {}}, pos)

    def if_node(self, name: str, conditions: list[tuple[str, str, Any]], pos: tuple[int, int], combinator: str = "and") -> str:
        """conditions : (expression gauche, opération, valeur droite). Sortie 0 = vrai, 1 = faux."""
        return self.node(name, "n8n-nodes-base.if", 2.2,
                         {"conditions": {"options": COND_OPTS, "conditions": [self._cond(name, i, *c) for i, c in enumerate(conditions)],
                                         "combinator": combinator}, "options": {}}, pos)

    def switch_node(self, name: str, rules: list[tuple[str, list[tuple[str, str, Any]]]], pos: tuple[int, int],
                    fallback: bool = True) -> str:
        values = []
        for key, conds in rules:
            values.append({
                "conditions": {"options": COND_OPTS,
                               "conditions": [self._cond(f"{name}:{key}", i, *c) for i, c in enumerate(conds)],
                               "combinator": "and"},
                "renameOutput": True,
                "outputKey": key,
            })
        options: dict[str, Any] = {"fallbackOutput": "extra", "renameFallbackOutput": "other"} if fallback else {}
        return self.node(name, "n8n-nodes-base.switch", 3.2, {"rules": {"values": values}, "options": options}, pos)

    def _cond(self, scope: str, i: int, left: str, op: str, right: Any) -> dict[str, Any]:
        typ, operation = op.split(":")
        operator: dict[str, Any] = {"type": typ, "operation": operation}
        cond: dict[str, Any] = {"id": str(uuid.uuid5(NS, f"{self.name}:{scope}:{i}")), "leftValue": left, "operator": operator}
        if operation in ("notEmpty", "empty", "true", "false", "exists", "notExists"):
            operator["singleValue"] = True
            cond["rightValue"] = ""
        else:
            cond["rightValue"] = right
        return cond

    def http(self, name: str, method: str, url: str, pos: tuple[int, int], *, body: str | None = None,
             headers: dict[str, str] | None = None, query: dict[str, str] | None = None,
             credentials: dict | None = None, auth: str = "genericCredentialType", timeout: int = 30000,
             on_error: str = "continueRegularOutput", notes: str | None = None, cred_type: str = "httpHeaderAuth") -> str:
        params: dict[str, Any] = {"method": method, "url": url}
        if credentials:
            if auth == "genericCredentialType":
                params.update({"authentication": "genericCredentialType", "genericAuthType": cred_type})
            else:
                params.update({"authentication": "predefinedCredentialType", "nodeCredentialType": cred_type})
        if query:
            params["sendQuery"] = True
            params["queryParameters"] = {"parameters": [{"name": k, "value": v} for k, v in query.items()]}
        if headers:
            params["sendHeaders"] = True
            params["headerParameters"] = {"parameters": [{"name": k, "value": v} for k, v in headers.items()]}
        if body is not None:
            params["sendBody"] = True
            params["specifyBody"] = "json"
            params["jsonBody"] = body
        # Pas d'exception sur 4xx/5xx : le workflow aiguille explicitement selon statusCode.
        params["options"] = {"timeout": timeout, "response": {"response": {"fullResponse": True, "neverError": True,
                                                                          "responseFormat": "json"}}}
        return self.node(name, "n8n-nodes-base.httpRequest", 4.2, params, pos, credentials=credentials, on_error=on_error,
                         notes=notes)

    # -- export --------------------------------------------------------------------------------------
    def validate(self) -> None:
        for src, outs in self.connections.items():
            assert src in self._names
            for branch in outs.get("main", []):
                for link in branch:
                    assert link["node"] in self._names, f"{src} -> {link['node']} inconnu"
        reachable: set[str] = set()
        triggers = [n["name"] for n in self.nodes if n["type"].endswith(("Trigger", "webhook"))]
        stack = list(triggers)
        while stack:
            cur = stack.pop()
            if cur in reachable:
                continue
            reachable.add(cur)
            for branch in self.connections.get(cur, {}).get("main", []):
                stack.extend(link["node"] for link in branch)
        orphans = [n["name"] for n in self.nodes if n["name"] not in reachable and n["type"] != "n8n-nodes-base.stickyNote"]
        assert not orphans, f"nœuds inaccessibles depuis un déclencheur : {orphans}"

    def export(self) -> dict[str, Any]:
        self.validate()
        return {
            "name": self.name,
            "nodes": self.nodes,
            "connections": self.connections,
            "active": False,  # livré DÉSACTIVÉ : l'activation est une décision humaine (IMPORT_GUIDE.md)
            "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all",
                         "saveManualExecutions": True, "executionTimeout": 600},
            "pinData": {},
            "meta": {"templateCredsSetupCompleted": False, "description": self.description},
            "tags": [],
        }

    def write(self, directory: Path, filename: str) -> Path:
        path = directory / filename
        path.write_text(json.dumps(self.export(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


# --- Expressions partagées ---------------------------------------------------------------------------
CFG = "$('LF Config').first().json"
API = f"{CFG}.api_base_url"


def expr(body: str) -> str:
    return "={{ " + body + " }}"


def url(path_expr: str) -> str:
    """URL de l'API interne : `path_expr` est une expression JS produisant le chemin (ex. "'/outbox/claim'")."""
    return "={{ " + API + " + " + path_expr + " }}"


def json_body(js_object: str) -> str:
    return "={{ JSON.stringify(" + js_object + ") }}"


def backend_headers(step: str | None = None, *, idempotent: bool = True) -> dict[str, str]:
    h = {
        "X-LF-Timestamp": "={{ Date.now() }}",
        "X-Correlation-ID": expr(f"{CFG}.correlation_id"),
    }
    if idempotent:
        h["Idempotency-Key"] = expr(f"{CFG}.event_id + ':' + {CFG}.attempt + ':{step}'")
    return h
