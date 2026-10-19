"""Remplaçant LOCAL de n8n (WF-04 + WF-01/02/03) pour développer et tester sans instance n8n.

Il exécute exactement la même séquence d'appels HTTP que les workflows exportés, avec les mêmes règles :
le backend reste l'unique autorité des retries (ce worker ne réessaie jamais lui-même).

    python -m scripts.dev_worker --base-url http://localhost:8000 --token $API_SERVICE_TOKEN --loop

Ce n'est PAS n8n : il ne valide pas les exports JSON. Il sert de référence exécutable et de moteur des tests E2E.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from typing import Any, Protocol


class HttpClient(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


class StandInWorker:
    def __init__(self, client: HttpClient, token: str, prefix: str = "/api/v1/internal", worker: str = "dev-worker"):
        self.client, self.token, self.prefix, self.worker = client, token, prefix, worker

    # -- transport ---------------------------------------------------------------------------------
    def call(self, method: str, path: str, *, json: dict | None = None, key: str | None = None,
             correlation_id: str | None = None):
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-LF-Timestamp": str(int(time.time() * 1000)),
            "X-Correlation-ID": correlation_id or str(uuid.uuid4()),
        }
        if key:
            headers["Idempotency-Key"] = key
        return self.client.request(method, f"{self.prefix}{path}", json=json, headers=headers)

    # -- boucle ------------------------------------------------------------------------------------
    def run_once(self, limit: int = 10) -> list[dict[str, Any]]:
        r = self.call("POST", "/outbox/claim", json={"limit": limit, "worker": self.worker})
        r.raise_for_status()
        results = []
        for ev in r.json()["events"]:
            try:
                outcome = self.handle(ev)
            except Exception as exc:  # noqa: BLE001 - rapporté au backend, qui décide du retry
                self._fail(ev, "WORKER_EXCEPTION", True, type(exc).__name__)
                outcome = "worker_exception"
            results.append({"event_id": ev["event_id"], "event_type": ev["event_type"], "outcome": outcome})
        return results

    def drain(self, max_rounds: int = 10) -> list[dict[str, Any]]:
        """Traite en chaîne les événements (qualification -> CRM + brouillon) jusqu'à file vide."""
        out: list[dict[str, Any]] = []
        for _ in range(max_rounds):
            batch = self.run_once()
            if not batch:
                break
            out.extend(batch)
        return out

    # -- routage (Switch du WF-04) -----------------------------------------------------------------
    def handle(self, ev: dict[str, Any]) -> str:
        etype = ev["event_type"]
        if etype == "LEAD_SUBMITTED":
            return self.wf01_qualification(ev)
        if etype == "CRM_SYNC_REQUESTED":
            return self.wf02_crm_sync(ev)
        if etype == "DRAFT_REQUESTED":
            return self.wf03_draft(ev)
        self._fail(ev, "UNKNOWN_EVENT_TYPE", False, etype)
        return "unknown_event_type"

    def _k(self, ev: dict[str, Any], step: str) -> str:
        return f"{ev['event_id']}:{ev['attempt']}:{step}"

    def _complete(self, ev, outcome: str = "SUCCEEDED") -> None:
        self.call("POST", f"/outbox/{ev['event_id']}/complete", json={"attempt": ev["attempt"], "outcome": outcome},
                  key=self._k(ev, "complete"), correlation_id=ev["correlation_id"]).raise_for_status()

    def _fail(self, ev, code: str, retryable: bool, message: str | None = None, retry_after: int | None = None) -> None:
        body: dict[str, Any] = {"attempt": ev["attempt"], "error_code": code, "retryable": retryable, "message": message}
        if retry_after is not None:
            body["retry_after_seconds"] = retry_after
        self.call("POST", f"/outbox/{ev['event_id']}/fail", json=body, key=self._k(ev, "fail"),
                  correlation_id=ev["correlation_id"]).raise_for_status()

    # -- WF-01 -------------------------------------------------------------------------------------
    def wf01_qualification(self, ev) -> str:
        cid, lead = ev["correlation_id"], ev["lead_id"]
        r = self.call("GET", f"/leads/{lead}/payload?event_id={ev['event_id']}", correlation_id=cid)
        r.raise_for_status()
        if r.json()["already_qualified_for_event"]:
            self._complete(ev)
            return "already_qualified"
        r = self.call("POST", f"/leads/{lead}/extract", json={"event_id": ev["event_id"]}, key=self._k(ev, "extract"),
                      correlation_id=cid)
        if r.status_code >= 500 or r.status_code in (401, 403, 409):
            err = r.json().get("error", {})
            self._fail(ev, err.get("code", f"HTTP_{r.status_code}"), bool(err.get("details", {}).get("retryable", False)))
            return "extract_failed"
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            self.call("POST", f"/leads/{lead}/manual-review",
                      json={"event_id": ev["event_id"], "error_code": data["error_code"]},
                      key=self._k(ev, "manual"), correlation_id=cid).raise_for_status()
            self._complete(ev, "MANUAL_REVIEW")
            return "manual_review"
        r = self.call("POST", f"/leads/{lead}/qualification", key=self._k(ev, "qualify"), correlation_id=cid, json={
            "event_id": ev["event_id"], "extraction": data["extraction"], "provider": data["provider"],
            "model_name": data["model"], "prompt_version": data["prompt_version"]})
        if r.status_code >= 400:
            self._fail(ev, f"QUALIFICATION_HTTP_{r.status_code}", r.status_code >= 500)
            return "qualification_failed"
        self._complete(ev)
        return "qualified"

    # -- WF-02 -------------------------------------------------------------------------------------
    def wf02_crm_sync(self, ev) -> str:
        cid, lead = ev["correlation_id"], ev["lead_id"]
        ctx = self.call("GET", f"/leads/{lead}/crm-context", correlation_id=cid)
        ctx.raise_for_status()
        if ctx.json()["provider"] != "mock":
            self._fail(ev, "HUBSPOT_NOT_SUPPORTED_BY_STANDIN", False, "Utiliser les workflows n8n pour HubSpot")
            return "unsupported_provider"
        r = self.call("POST", f"/leads/{lead}/crm/mock-upsert", json={"event_id": ev["event_id"]},
                      key=self._k(ev, "crm-upsert"), correlation_id=cid)
        if r.status_code >= 500:
            self._fail(ev, "CRM_MOCK_ERROR", True)
            return "crm_failed"
        r.raise_for_status()
        up = r.json()
        self.call("POST", f"/leads/{lead}/crm-sync", key=self._k(ev, "crm-record"), correlation_id=cid, json={
            "event_id": ev["event_id"], "provider": "mock", "status": "SYNCED",
            "external_contact_id": up["external_contact_id"], "action": up["action"]}).raise_for_status()
        self._complete(ev)
        return "synced"

    # -- WF-03 -------------------------------------------------------------------------------------
    def wf03_draft(self, ev) -> str:
        cid, lead = ev["correlation_id"], ev["lead_id"]
        r = self.call("POST", f"/leads/{lead}/draft/generate", json={"event_id": ev["event_id"]},
                      key=self._k(ev, "draft-gen"), correlation_id=cid)
        if r.status_code >= 500:
            err = r.json().get("error", {})
            self._fail(ev, err.get("code", f"HTTP_{r.status_code}"), bool(err.get("details", {}).get("retryable", False)))
            return "draft_failed"
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            self._complete(ev, "MANUAL_REVIEW")  # brouillon refusé par la politique : revue humaine, pas de retry
            return "draft_rejected_by_policy"
        r = self.call("POST", f"/leads/{lead}/followups", key=self._k(ev, "draft-create"), correlation_id=cid, json={
            "event_id": ev["event_id"], "draft": data["draft"], "provider": data["provider"],
            "model_name": data["model"], "prompt_version": data["prompt_version"]})
        if r.status_code >= 400:
            self._fail(ev, f"FOLLOWUP_HTTP_{r.status_code}", r.status_code >= 500)
            return "followup_failed"
        self._complete(ev)
        return "draft_created"


def main() -> None:
    import httpx

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default=os.getenv("LEADFLOW_API_URL", "http://localhost:8000"))
    p.add_argument("--token", default=os.getenv("API_SERVICE_TOKEN", ""))
    p.add_argument("--loop", action="store_true", help="interroge l'API toutes les --interval secondes")
    p.add_argument("--drain", action="store_true", help="traite en chaîne (qualification -> CRM + brouillon) jusqu'à file vide, puis quitte")
    p.add_argument("--interval", type=float, default=5.0)
    args = p.parse_args()
    if not args.token:
        sys.exit("API_SERVICE_TOKEN requis (--token ou variable d'environnement)")
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        worker = StandInWorker(client, args.token)
        if args.drain:
            for res in worker.drain():
                print(res, flush=True)
            return
        while True:
            for res in worker.run_once():
                print(res, flush=True)
            if not args.loop:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
