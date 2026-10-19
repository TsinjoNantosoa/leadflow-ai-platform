"""Faux HubSpot (API contacts v3) pour valider LF-WF-02 en local, avec injection de pannes PAR E-MAIL.

    python automation/n8n/tools/fake_hubspot.py --port 9100

Ce n'est pas HubSpot : il reproduit uniquement les formes de requêtes/réponses utilisées par le workflow
(search, create avec 409 « Existing ID », update) afin d'exercer les chemins 429 / 401 / 5xx / timeout / doublon.

Pilotage : POST /__scenario {"email": "x@example.org", "op": "search|create|update", "behaviours": ["429", "ok"]}
  comportements : ok | 429 | 401 | 403 | 500 | drop (crée la fiche puis ne répond qu'après 25 s => timeout côté n8n)
Inspection : GET /__state  (contacts + journal des appels) ; POST /__reset
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
CONTACTS: dict[str, dict] = {}
SCENARIOS: dict[tuple[str, str], list[str]] = {}
CALLS: list[dict] = []
NEXT_ID = [1000]


def _next_behaviour(email: str, op: str) -> str:
    q = SCENARIOS.get((email, op))
    return q.pop(0) if q else "ok"


def _by_email(email: str) -> tuple[str, dict] | None:
    for cid, c in CONTACTS.items():
        if c["properties"].get("email") == email:
            return cid, c
    return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencieux
        pass

    def _send(self, status: int, body: dict, headers: dict | None = None):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _inject(self, behaviour: str) -> bool:
        if behaviour == "429":
            self._send(429, {"status": "error", "message": "rate limit", "category": "RATE_LIMITS"}, {"Retry-After": "7"})
        elif behaviour in ("401", "403"):
            self._send(int(behaviour), {"status": "error", "message": "invalid token", "category": "INVALID_AUTHENTICATION"})
        elif behaviour == "500":
            self._send(500, {"status": "error", "message": "boom"})
        else:
            return False
        return True

    def do_POST(self):  # noqa: N802
        if self.path == "/__reset":
            with LOCK:
                CONTACTS.clear(); SCENARIOS.clear(); CALLS.clear()
            return self._send(200, {"ok": True})
        body = self._body()
        if self.path == "/__scenario":
            with LOCK:
                SCENARIOS[(body["email"], body["op"])] = list(body["behaviours"])
            return self._send(200, {"ok": True})

        if self.path == "/crm/v3/objects/contacts/search":
            email = body["filterGroups"][0]["filters"][0]["value"]
            with LOCK:
                CALLS.append({"op": "search", "email": email, "auth": bool(self.headers.get("Authorization"))})
                beh = _next_behaviour(email, "search")
                if self._inject(beh):
                    return
                found = _by_email(email)
            results = [{"id": found[0], "properties": found[1]["properties"]}] if found else []
            return self._send(200, {"total": len(results), "results": results})

        if self.path == "/crm/v3/objects/contacts":
            props = body.get("properties", {})
            email = props.get("email", "")
            with LOCK:
                CALLS.append({"op": "create", "email": email})
                beh = _next_behaviour(email, "create")
                if self._inject(beh):
                    return
                existing = _by_email(email)
                if existing:
                    return self._send(409, {"status": "error", "category": "CONFLICT",
                                            "message": f"Contact already exists. Existing ID: {existing[0]}"})
                cid = str(NEXT_ID[0]); NEXT_ID[0] += 1
                CONTACTS[cid] = {"properties": props}
            if beh == "drop":  # la fiche EST créée, mais la réponse arrive trop tard
                time.sleep(25)
            return self._send(201, {"id": cid, "properties": props})
        self._send(404, {"message": "not found"})

    def do_PATCH(self):  # noqa: N802
        m = re.fullmatch(r"/crm/v3/objects/contacts/(\d+)", self.path)
        body = self._body()
        if not m:
            return self._send(404, {"message": "not found"})
        cid = m.group(1)
        with LOCK:
            c = CONTACTS.get(cid)
            email = (c or {}).get("properties", {}).get("email", "")
            CALLS.append({"op": "update", "email": email, "id": cid})
            if self._inject(_next_behaviour(email, "update")):
                return
            if c is None:
                return self._send(404, {"status": "error", "message": "contact not found"})
            c["properties"].update(body.get("properties", {}))
        self._send(200, {"id": cid, "properties": c["properties"]})

    def do_GET(self):  # noqa: N802
        if self.path == "/__state":
            with LOCK:
                return self._send(200, {"contacts": CONTACTS, "calls": CALLS})
        self._send(404, {"message": "not found"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9100)
    args = ap.parse_args()
    print(f"fake HubSpot sur :{args.port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
