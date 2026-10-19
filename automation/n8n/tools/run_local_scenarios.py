"""Scénarios de validation des workflows n8n sur une instance LOCALE de test (jamais l'instance OVH).

Prérequis (voir automation/n8n/README.md, section « Validation locale ») :
  - backend lancé avec CRM_PROVIDER=hubspot, OUTBOX_BACKOFF_BASE_SECONDS=5 (base de test dédiée) ;
  - faux HubSpot lancé (fake_hubspot.py) et workflows importés/publiés dans l'n8n local avec les URL de test ;
  - WF-04 actif (planification 1 min).

    python automation/n8n/tools/run_local_scenarios.py --api http://localhost:8000 --hubspot http://localhost:9100 \\
        --database-url postgresql+psycopg://leadflow:leadflow_local@localhost:5433/leadflow_e2e --timeout 900

Le script soumet des demandes fictives, attend que le système se stabilise, puis vérifie l'état en base ET côté faux HubSpot.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx
from sqlalchemy import create_engine, text

MSG = "Bonjour, nous voulons automatiser notre support client. Budget 3000 EUR, démarrage dans un mois."

SCENARIOS = {
    "A_create": dict(email="hs-a@example.org", message=MSG, hubspot={}),
    "C_rate_limit_then_ok": dict(email="hs-c@example.org", message=MSG, hubspot={("search"): ["429"]}),
    "D_timeout_after_success": dict(email="hs-d@example.org", message=MSG, hubspot={("create"): ["drop"]}),
    "E_auth_401": dict(email="hs-e@example.org", message=MSG, hubspot={("search"): ["401"] * 10}),
    "F_llm_invalid": dict(email="hs-f@example.org", message=MSG + " [[mock:invalid]]", hubspot={}),
    "G_llm_transient": dict(email="hs-g@example.org", message=MSG + " [[mock:timeout]]", hubspot={}),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--hubspot", default="http://localhost:9100")
    ap.add_argument("--database-url", required=True)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()
    db = create_engine(args.database_url)
    hs = httpx.Client(base_url=args.hubspot, timeout=10)
    api = httpx.Client(base_url=args.api, timeout=20)
    hs.post("/__reset")

    leads: dict[str, str] = {}
    for name, sc in SCENARIOS.items():
        for op, beh in sc["hubspot"].items():
            hs.post("/__scenario", json={"email": sc["email"], "op": op, "behaviours": beh})
    for name, sc in SCENARIOS.items():
        r = api.post("/api/v1/public/leads", headers={"Idempotency-Key": str(uuid.uuid4())}, json={
            "full_name": f"Scenario {name}", "email": sc["email"], "company": "Scenario Co", "requested_service": "customer_support_automation",
            "message": sc["message"], "consent_privacy": True, "consent_marketing": False})
        r.raise_for_status()
        leads[name] = r.json()["lead_id"]
        print(f"soumis {name}: {leads[name]}", flush=True)
    # B : même e-mail que A, soumis après A (le contact HubSpot existera => mise à jour sans doublon)
    time.sleep(1)

    def snapshot():
        with db.connect() as c:
            return {
                "leads": {r[0]: (r[1], r[2]) for r in c.execute(text("select id::text,status,status_reason from leads"))},
                "events": c.execute(text("select l.id::text, e.event_type, e.status, e.attempt_count, e.last_error_code from outbox_events e join leads l on l.id=e.lead_id order by e.created_at")).all(),
                "crm": {r[0]: (r[1], r[2], r[3]) for r in c.execute(text("select co.email_normalized, m.sync_status, m.last_error_code, m.external_contact_id from crm_mappings m join contacts co on co.id=m.contact_id"))},
            }

    def settled(s):
        for lid in leads.values():
            evs = [e for e in s["events"] if e[0] == lid]
            if not evs or any(e[2] in ("PENDING", "PROCESSING") for e in evs):
                return False
        return True

    deadline = time.time() + args.timeout
    b_submitted = False
    while time.time() < deadline:
        s = snapshot()
        if not b_submitted and s["crm"].get("hs-a@example.org", ("",))[0] == "SYNCED":
            r = api.post("/api/v1/public/leads", headers={"Idempotency-Key": str(uuid.uuid4())}, json={
                "full_name": "Scenario B", "email": "hs-a@example.org", "company": "Scenario Co", "requested_service": "data_dashboard",
                "message": "Seconde demande du même contact : un tableau de bord de suivi, budget 2500 EUR sous 2 semaines.",
                "consent_privacy": True, "consent_marketing": False})
            leads["B_update_existing"] = r.json()["lead_id"]
            b_submitted = True
            print("soumis B_update_existing", flush=True)
        # G (erreur LLM transitoire) reste RETRYING/dead-letter : on ne l'attend pas indéfiniment
        pending = [n for n, lid in leads.items() if n != "G_llm_transient" and any(e[0] == lid and e[2] in ("PENDING", "PROCESSING", "RETRYING") and not (n == "C_rate_limit_then_ok" and False) for e in s["events"])]
        if b_submitted and not pending and all(any(e[0] == lid for e in s["events"]) for lid in leads.values()):
            break
        time.sleep(10)

    s = snapshot()
    state = hs.get("/__state").json()
    hs_by_email: dict[str, int] = {}
    for c in state["contacts"].values():
        hs_by_email[c["properties"]["email"]] = hs_by_email.get(c["properties"]["email"], 0) + 1

    ok = True

    def check(label: str, cond: bool, info: str = ""):
        nonlocal ok
        ok &= cond
        print(f"[{'OK' if cond else 'ÉCHEC'}] {label} {info}", flush=True)

    L = lambda n: s["leads"].get(leads[n], ("?", None))  # noqa: E731
    ev = lambda n, t: [e for e in s["events"] if e[0] == leads[n] and e[1] == t]  # noqa: E731
    check("A : lead READY, CRM SYNCED", L("A_create")[0] == "READY" and s["crm"]["hs-a@example.org"][0] == "SYNCED", str(L("A_create")))
    check("A : une seule fiche HubSpot", hs_by_email.get("hs-a@example.org") == 1, str(hs_by_email))
    check("B : second lead du même contact traité par MISE À JOUR (toujours 1 fiche)", L("B_update_existing")[0] == "READY"
          and any(c["op"] == "update" and c["email"] == "hs-a@example.org" for c in state["calls"]), str(L("B_update_existing")))
    c_ev = ev("C_rate_limit_then_ok", "CRM_SYNC_REQUESTED")
    check("C : 429 puis succès après retry (backend)", c_ev and c_ev[0][2] == "DELIVERED" and c_ev[0][3] >= 2 and s["crm"]["hs-c@example.org"][0] == "SYNCED", str(c_ev))
    d_ev = ev("D_timeout_after_success", "CRM_SYNC_REQUESTED")
    check("D : succès côté CRM puis timeout => reprise SANS second contact", hs_by_email.get("hs-d@example.org") == 1 and d_ev and d_ev[0][2] == "DELIVERED" and d_ev[0][3] >= 2,
          f"{d_ev} fiches={hs_by_email.get('hs-d@example.org')}")
    e_ev = ev("E_auth_401", "CRM_SYNC_REQUESTED")
    check("E : 401 => erreur de configuration, dead-letter immédiat, mapping FAILED, lead conservé", e_ev and e_ev[0][2] == "DEAD_LETTER"
          and s["crm"]["hs-e@example.org"][0] == "FAILED" and L("E_auth_401")[0] in ("QUALIFIED", "READY"), f"{e_ev} {L('E_auth_401')}")
    check("F : sortie LLM invalide => MANUAL_REVIEW sans événement CRM", L("F_llm_invalid")[0] == "MANUAL_REVIEW" and not ev("F_llm_invalid", "CRM_SYNC_REQUESTED"), str(L("F_llm_invalid")))
    g_ev = ev("G_llm_transient", "LEAD_SUBMITTED")
    check("G : panne LLM => reprise planifiée par le backend (RETRYING ou DEAD_LETTER), lead conservé", g_ev and g_ev[0][2] in ("RETRYING", "DEAD_LETTER", "PROCESSING") and g_ev[0][3] >= 1, str(g_ev))
    print("\nRÉSULTAT :", "TOUS LES SCÉNARIOS VALIDÉS" if ok else "ÉCHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
