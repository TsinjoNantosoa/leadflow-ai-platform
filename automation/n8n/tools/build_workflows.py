"""Génère les 4 exports n8n LeadFlow AI.   python automation/n8n/tools/build_workflows.py

Sortie : automation/n8n/WF-0X-*.json (désactivés, sans secret, placeholders explicites).
Cible : n8n >= 1.100 (testé sur 2.43.8) ; nœuds : Webhook v2, HTTP Request v4.2, IF v2.2, Switch v3.2, Set v3.4.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from n8n_builder import (  # noqa: E402
    API_PLACEHOLDER,
    CFG,
    CRED_API,
    CRED_HUBSPOT,
    CRED_WEBHOOK_HEADER,
    N8N_PLACEHOLDER,
    Workflow,
    backend_headers,
    expr,
    json_body,
    url,
)

OUT = Path(__file__).resolve().parents[1]
POLL_MINUTES = 20  # filet de récupération ; surchargeable : python build_workflows.py --poll-minutes 30
EV = CFG  # alias lisible : $('LF Config').first().json


# ---------------------------------------------------------------------------------------------------
# Briques communes aux workflows « enfants » (WF-01/02/03)
# ---------------------------------------------------------------------------------------------------
def child_preamble(wf: Workflow, path: str) -> str:
    wf.node("Webhook", "n8n-nodes-base.webhook", 2,
            {"httpMethod": "POST", "path": path, "authentication": "headerAuth", "responseMode": "responseNode", "options": {}},
            (0, 300), credentials=CRED_WEBHOOK_HEADER, webhook=True,
            notes="Appelé UNIQUEMENT par LF-WF-04 (secret d'en-tête). Corps = événement réservé par le backend.")
    wf.node("Respond Accepted", "n8n-nodes-base.respondToWebhook", 1.1,
            {"respondWith": "json", "responseBody": "={{ JSON.stringify({ accepted: true, event_id: $json.body.event_id }) }}",
             "options": {"responseCode": 202}}, (240, 300),
            notes="Accusé de réception seulement : HTTP 202 ne signifie PAS que le traitement métier est terminé.")
    wf.set_node("LF Config", {
        "api_base_url": API_PLACEHOLDER,
        "event_id": "={{ $('Webhook').first().json.body.event_id }}",
        "lead_id": "={{ $('Webhook').first().json.body.lead_id }}",
        "correlation_id": "={{ $('Webhook').first().json.body.correlation_id }}",
        "attempt": ("={{ Number($('Webhook').first().json.body.attempt) }}", "number"),
        "run_id": "={{ $('Webhook').first().json.body.run_id }}",
    }, (480, 300))
    wf.chain("Webhook", "Respond Accepted", "LF Config")
    wf.note("**À MODIFIER après import** : `api_base_url` = URL HTTPS de votre API FastAPI + `/api/v1/internal` "
            "(sans slash final). Credentials : voir IMPORT_GUIDE.md. Aucun secret n'est stocké dans ce JSON.",
            (440, 120), (380, 130), 3)
    return "LF Config"


def fail_set(wf: Workflow, name: str, code: str, retryable: str, message: str, pos: tuple[int, int], *,
             record_crm: bool | None = None, retry_after: str | None = None) -> str:
    fields: dict = {
        "fail_error_code": code,
        "fail_retryable": (retryable, "boolean"),
        "fail_message": message,
        "fail_retry_after": (retry_after or "={{ 0 }}", "number"),
    }
    if record_crm is not None:
        fields["fail_record_crm"] = (record_crm, "boolean")
    return wf.set_node(name, fields, pos)


def http_status_code(prefix: str) -> str:
    return "={{ '" + prefix + "' + ($json.statusCode || 'NO_RESPONSE') }}"


RETRYABLE_HTTP = "={{ !$json.statusCode || $json.statusCode >= 500 || $json.statusCode === 429 }}"


def failure_tail(wf: Workflow, join: str, x: int, y: int) -> str:
    """Nœud final commun : le BACKEND décide retry/dead-letter, n8n ne réessaie jamais lui-même."""
    f = f"$('{join}').first().json"
    wf.http("Report Failure", "POST", url(f"'/outbox/' + {EV}.event_id + '/fail'"), (x, y),
            body=json_body("{ attempt: " + EV + ".attempt, error_code: " + f + ".fail_error_code, retryable: " + f + ".fail_retryable, "
                           "message: " + f + ".fail_message, retry_after_seconds: " + f + ".fail_retry_after || undefined }"),
            headers=backend_headers("fail"), credentials=CRED_API,
            notes="Le backend applique backoff exponentiel, nombre max de tentatives et dead-letter (autorité unique des retries).")
    return "Report Failure"


def complete_node(wf: Workflow, name: str, outcome: str, pos: tuple[int, int], workflow_id: str, reason: str | None = None) -> str:
    details = "{ workflow: '" + workflow_id + "'" + (f", reason: '{reason}'" if reason else "") + " }"
    return wf.http(name, "POST", url(f"'/outbox/' + {EV}.event_id + '/complete'"), pos,
                   body=json_body("{ attempt: " + EV + ".attempt, outcome: '" + outcome + "', details: " + details + " }"),
                   headers=backend_headers("complete"), credentials=CRED_API)


# ---------------------------------------------------------------------------------------------------
# WF-01 — Lead Qualification
# ---------------------------------------------------------------------------------------------------
def wf01() -> Workflow:
    wf = Workflow("LF-WF-01 Lead Qualification",
                  "Événement LEAD_SUBMITTED -> extraction OpenAI (via FastAPI) -> score serveur -> qualification persistée.")
    child_preamble(wf, "lf-wf-01-lead-qualification")

    wf.http("Get Lead Payload", "GET", url(f"'/leads/' + {EV}.lead_id + '/payload'"), (720, 300),
            query={"event_id": expr(f"{EV}.event_id")}, headers=backend_headers(idempotent=False), credentials=CRED_API)
    wf.if_node("Payload OK?", [("={{ $json.statusCode }}", "number:equals", 200)], (960, 300))
    wf.if_node("Already Qualified?", [("={{ $json.body.already_qualified_for_event }}", "boolean:true", None)], (1200, 240))
    wf.http("Extract With LLM", "POST", url(f"'/leads/' + {EV}.lead_id + '/extract'"), (1440, 300),
            body=json_body("{ event_id: " + EV + ".event_id }"), headers=backend_headers("extract"), credentials=CRED_API,
            timeout=110000, notes="FastAPI appelle OpenAI (ou le mock). Aucune clé OpenAI n'est présente dans n8n.")
    wf.switch_node("Classify Extraction", [
        ("extracted", [("={{ $json.statusCode }}", "number:equals", 200), ("={{ $json.body.ok }}", "boolean:true", None)]),
        ("manual_review", [("={{ $json.statusCode }}", "number:equals", 200), ("={{ $json.body.ok }}", "boolean:false", None)]),
        ("transient", [("={{ !$json.statusCode || $json.statusCode >= 500 }}", "boolean:true", None)]),
    ], (1680, 300))
    wf.if_node("Validate Extraction", [
        ("={{ $json.body.extraction.intent }}", "string:notEmpty", None),
        ("={{ $json.body.extraction.service }}", "string:notEmpty", None),
        ("={{ $json.body.extraction.language }}", "string:notEmpty", None),
        ("={{ $json.body.extraction.need_clarity }}", "string:notEmpty", None),
        ("={{ $json.body.extraction.summary }}", "string:notEmpty", None),
    ], (1920, 180))
    wf.http("Log Step: extraction validated", "POST", url(f"'/runs/' + {EV}.run_id + '/status'"), (2160, 120),
            body=json_body("{ step: 'extraction_validated', note: 'schema ok' }"), headers=backend_headers("step-validated"),
            credentials=CRED_API, notes="Journal informatif : un échec ici n'interrompt pas le traitement.")
    wf.http("Save Qualification", "POST", url(f"'/leads/' + {EV}.lead_id + '/qualification'"), (2400, 120),
            body=json_body("{ event_id: " + EV + ".event_id, extraction: $('Extract With LLM').first().json.body.extraction, "
                           "provider: $('Extract With LLM').first().json.body.provider, "
                           "model_name: $('Extract With LLM').first().json.body.model, "
                           "prompt_version: $('Extract With LLM').first().json.body.prompt_version }"),
            headers=backend_headers("qualify"), credentials=CRED_API,
            notes="Le score est calculé par FastAPI (règles scoring-v1), jamais par le LLM.")
    wf.if_node("Qualification Saved?", [("={{ $json.statusCode }}", "number:equals", 200)], (2640, 120))
    wf.http("Log Step: qualification saved", "POST", url(f"'/runs/' + {EV}.run_id + '/status'"), (2880, 60),
            body=json_body("{ step: 'qualification_saved', note: 'CRM_SYNC_REQUESTED + DRAFT_REQUESTED emitted by backend' }"),
            headers=backend_headers("step-saved"), credentials=CRED_API)
    complete_node(wf, "Complete Event", "SUCCEEDED", (3120, 120), "LF-WF-01")

    # revue manuelle (refus / sortie invalide / extraction incomplète côté workflow)
    wf.set_node("Manual Review: LLM outcome", {"review_error_code": "={{ $json.body.error_code }}"}, (1920, 420))
    wf.set_node("Manual Review: invalid extraction", {"review_error_code": "EXTRACTION_INVALID_AT_WORKFLOW"}, (2160, 300))
    wf.http("Mark Manual Review", "POST", url(f"'/leads/' + {EV}.lead_id + '/manual-review'"), (2400, 400),
            body=json_body("{ event_id: " + EV + ".event_id, error_code: $json.review_error_code, "
                           "detail: 'Qualification automatique impossible : revue humaine requise' }"),
            headers=backend_headers("manual"), credentials=CRED_API)
    wf.if_node("Manual Review Marked?", [("={{ $json.statusCode }}", "number:equals", 200)], (2640, 400))
    complete_node(wf, "Complete (manual review)", "MANUAL_REVIEW", (2880, 380), "LF-WF-01", "manual_review")

    # échecs
    fail_set(wf, "Fail: Payload Error", http_status_code("PAYLOAD_HTTP_"), RETRYABLE_HTTP, "Lecture du lead impossible", (1200, 560))
    fail_set(wf, "Fail: LLM Transient", "={{ $json.body?.error?.code || 'LLM_NO_RESPONSE' }}",
             "={{ $json.body?.error?.details?.retryable ?? true }}", "Service IA indisponible", (1920, 560))
    fail_set(wf, "Fail: Extraction Rejected", http_status_code("EXTRACT_HTTP_"), "={{ false }}", "Extraction refusée par le backend", (1920, 680))
    fail_set(wf, "Fail: Save Error", http_status_code("SAVE_HTTP_"), RETRYABLE_HTTP, "Enregistrement impossible", (2880, 520))
    wf.node("Failure Info", "n8n-nodes-base.noOp", 1, {}, (3120, 600))
    failure_tail(wf, "Failure Info", 3360, 600)

    # câblage
    wf.connect("LF Config", "Get Lead Payload")
    wf.connect("Get Lead Payload", "Payload OK?")
    wf.connect("Payload OK?", "Already Qualified?", 0)
    wf.connect("Payload OK?", "Fail: Payload Error", 1)
    wf.connect("Already Qualified?", "Complete Event", 0)
    wf.connect("Already Qualified?", "Extract With LLM", 1)
    wf.connect("Extract With LLM", "Classify Extraction")
    wf.connect("Classify Extraction", "Validate Extraction", 0)
    wf.connect("Classify Extraction", "Manual Review: LLM outcome", 1)
    wf.connect("Classify Extraction", "Fail: LLM Transient", 2)
    wf.connect("Classify Extraction", "Fail: Extraction Rejected", 3)
    wf.connect("Validate Extraction", "Log Step: extraction validated", 0)
    wf.connect("Validate Extraction", "Manual Review: invalid extraction", 1)
    wf.chain("Log Step: extraction validated", "Save Qualification", "Qualification Saved?")
    wf.connect("Qualification Saved?", "Log Step: qualification saved", 0)
    wf.connect("Qualification Saved?", "Fail: Save Error", 1)
    wf.connect("Log Step: qualification saved", "Complete Event")
    wf.connect("Manual Review: LLM outcome", "Mark Manual Review")
    wf.connect("Manual Review: invalid extraction", "Mark Manual Review")
    wf.connect("Mark Manual Review", "Manual Review Marked?")
    wf.connect("Manual Review Marked?", "Complete (manual review)", 0)
    wf.connect("Manual Review Marked?", "Fail: Save Error", 1)
    for f in ("Fail: Payload Error", "Fail: LLM Transient", "Fail: Extraction Rejected", "Fail: Save Error"):
        wf.connect(f, "Failure Info")
    wf.connect("Failure Info", "Report Failure")
    wf.note("**LF-WF-01 — Qualification.** Webhook (secret) → lecture lead → idempotence → extraction (FastAPI→OpenAI) → "
            "validation → score serveur → complétion. Refus/JSON invalide → revue manuelle. Panne → /fail (le backend décide du retry).",
            (0, 40), (420, 170), 7)
    return wf


# ---------------------------------------------------------------------------------------------------
# WF-02 — HubSpot CRM Sync
# ---------------------------------------------------------------------------------------------------
HS = "https://api.hubapi.com/crm/v3/objects/contacts"
CTX = "$('Get CRM Context').first().json.body"


def hs_properties() -> str:
    return ("{ properties: { email: " + CTX + ".contact.email_normalized, "
            "firstname: " + CTX + ".contact.full_name.split(' ')[0], "
            "lastname: " + CTX + ".contact.full_name.split(' ').slice(1).join(' ') || undefined, "
            "company: " + CTX + ".contact.company || undefined, phone: " + CTX + ".contact.phone || undefined } }")


def classify_hubspot(wf: Workflow, name: str, ok_rules: list, pos: tuple[int, int]) -> str:
    return wf.switch_node(name, [
        *ok_rules,
        ("rate_limited", [("={{ $json.statusCode }}", "number:equals", 429)]),
        ("auth_error", [("={{ [401, 403].includes($json.statusCode) }}", "boolean:true", None)]),
        ("transient", [("={{ !$json.statusCode || $json.statusCode >= 500 }}", "boolean:true", None)]),
    ], pos)


def wf02() -> Workflow:
    wf = Workflow("LF-WF-02 HubSpot CRM Sync",
                  "Événement CRM_SYNC_REQUESTED -> CRM_PROVIDER (mock | hubspot) -> upsert idempotent -> résultat enregistré.")
    child_preamble(wf, "lf-wf-02-crm-sync")

    wf.http("Get CRM Context", "GET", url(f"'/leads/' + {EV}.lead_id + '/crm-context'"), (720, 300),
            headers=backend_headers(idempotent=False), credentials=CRED_API)
    wf.if_node("Context OK?", [("={{ $json.statusCode }}", "number:equals", 200)], (960, 300))
    wf.switch_node("Route By CRM_PROVIDER", [
        ("mock", [("={{ $json.body.provider }}", "string:equals", "mock")]),
        ("hubspot", [("={{ $json.body.provider }}", "string:equals", "hubspot")]),
    ], (1200, 240))

    # --- mode mock (aucun credential) ---
    wf.http("Mock CRM Upsert", "POST", url(f"'/leads/' + {EV}.lead_id + '/crm/mock-upsert'"), (1440, 100),
            body=json_body("{ event_id: " + EV + ".event_id }"), headers=backend_headers("mock-upsert"), credentials=CRED_API,
            notes="CRM factice côté FastAPI : recherche + création/mise à jour idempotentes, sans credentials HubSpot.")
    wf.if_node("Mock Upsert OK?", [("={{ $json.statusCode }}", "number:equals", 200)], (1680, 100))
    wf.set_node("Prepare Sync Result (mock)", {
        "sync_provider": "mock", "sync_external_id": "={{ $json.body.external_contact_id }}",
        "sync_action": "={{ $json.body.action }}"}, (1920, 40))

    # --- mode HubSpot ---
    wf.if_node("Known External ID?", [
        (f"={{{{ {CTX}.mapping?.external_contact_id || '' }}}}", "string:notEmpty", None)], (1440, 420))
    wf.set_node("Prepare Update (known id)", {"hs_contact_id": expr(f"{CTX}.mapping.external_contact_id")}, (1680, 360))
    wf.http("HubSpot: Search Contact", "POST", HS + "/search", (1680, 520),
            body=json_body("{ filterGroups: [{ filters: [{ propertyName: 'email', operator: 'EQ', value: "
                           + CTX + ".contact.email_normalized }] }], properties: ['email','firstname','lastname','company','phone'], limit: 1 }"),
            headers={"X-Correlation-ID": expr(f"{EV}.correlation_id")}, credentials=CRED_HUBSPOT, auth="predefinedCredentialType",
            cred_type="hubspotAppToken", timeout=20000,
            notes="Recherche par e-mail normalisé AVANT toute création : réconcilie un succès dont la réponse s'est perdue (timeout).")
    classify_hubspot(wf, "Classify Search", [
        ("found", [("={{ $json.statusCode }}", "number:equals", 200), ("={{ $json.body.total }}", "number:gt", 0)]),
        ("not_found", [("={{ $json.statusCode }}", "number:equals", 200), ("={{ $json.body.total }}", "number:equals", 0)]),
    ], (1920, 520))
    wf.set_node("Prepare Update (from search)", {"hs_contact_id": "={{ $json.body.results[0].id }}"}, (2160, 440))
    wf.http("HubSpot: Update Contact", "PATCH", "={{ '" + HS + "/' + $json.hs_contact_id }}", (2400, 400),
            body=json_body(hs_properties()), headers={"X-Correlation-ID": expr(f"{EV}.correlation_id")},
            credentials=CRED_HUBSPOT, auth="predefinedCredentialType", cred_type="hubspotAppToken", timeout=20000)
    classify_hubspot(wf, "Classify Update", [
        ("ok", [("={{ [200, 201].includes($json.statusCode) }}", "boolean:true", None)]),
    ], (2640, 400))
    wf.http("HubSpot: Create Contact", "POST", HS, (2400, 600),
            body=json_body(hs_properties()), headers={"X-Correlation-ID": expr(f"{EV}.correlation_id")},
            credentials=CRED_HUBSPOT, auth="predefinedCredentialType", cred_type="hubspotAppToken", timeout=20000)
    classify_hubspot(wf, "Classify Create", [
        ("ok", [("={{ [200, 201].includes($json.statusCode) }}", "boolean:true", None)]),
        ("already_exists", [("={{ $json.statusCode }}", "number:equals", 409)]),
    ], (2640, 600))
    wf.set_node("Reconcile Existing Contact", {
        "hs_contact_id": "={{ (String($json.body.message || '').match(/Existing ID: (\\d+)/) || [])[1] || '' }}"}, (2880, 700))
    wf.if_node("Reconciled?", [("={{ $json.hs_contact_id }}", "string:notEmpty", None)], (3120, 700))
    wf.set_node("Prepare Result (hubspot update)", {
        "sync_provider": "hubspot", "sync_external_id": "={{ String($json.body.id) }}", "sync_action": "updated"}, (2880, 360))
    wf.set_node("Prepare Result (hubspot create)", {
        "sync_provider": "hubspot", "sync_external_id": "={{ String($json.body.id) }}", "sync_action": "created"}, (2880, 560))

    # --- enregistrement du résultat ---
    wf.http("Record CRM Sync", "POST", url(f"'/leads/' + {EV}.lead_id + '/crm-sync'"), (3360, 200),
            body=json_body("{ event_id: " + EV + ".event_id, provider: $json.sync_provider, status: 'SYNCED', "
                           "external_contact_id: $json.sync_external_id, action: $json.sync_action }"),
            headers=backend_headers("crm-record"), credentials=CRED_API)
    wf.if_node("Sync Recorded?", [("={{ $json.statusCode }}", "number:equals", 200)], (3600, 200))
    complete_node(wf, "Complete Event", "SUCCEEDED", (3840, 160), "LF-WF-02")

    # --- échecs (join unique -> enregistrement de l'état CRM -> rapport au backend) ---
    fail_set(wf, "Fail: Context Error", http_status_code("CONTEXT_HTTP_"), RETRYABLE_HTTP, "Contexte CRM illisible", (960, 900), record_crm=False)
    fail_set(wf, "Fail: Unknown Provider", "UNKNOWN_CRM_PROVIDER", "={{ false }}", "CRM_PROVIDER inconnu", (1200, 900), record_crm=False)
    fail_set(wf, "Fail: Mock CRM Error", http_status_code("MOCK_CRM_HTTP_"), RETRYABLE_HTTP, "CRM factice en erreur", (1680, 900), record_crm=True)
    fail_set(wf, "Fail: Rate Limited", "HUBSPOT_RATE_LIMITED", "={{ true }}", "HubSpot 429 : limite de débit", (2160, 900),
             record_crm=True, retry_after="={{ Number($json.headers?.['retry-after']) || 0 }}")
    fail_set(wf, "Fail: Auth Error", http_status_code("HUBSPOT_AUTH_"), "={{ false }}",
             "401/403 : vérifier le credential HubSpot (configuration, pas une panne passagère)", (2400, 900), record_crm=True)
    fail_set(wf, "Fail: Transient", "={{ $json.statusCode ? 'HUBSPOT_HTTP_' + $json.statusCode : 'HUBSPOT_NETWORK_TIMEOUT' }}",
             "={{ true }}", "Erreur serveur ou timeout : reprise sûre (recherche avant création)", (2640, 900), record_crm=True)
    fail_set(wf, "Fail: Client Error", http_status_code("HUBSPOT_HTTP_"), "={{ false }}", "Requête HubSpot refusée (4xx)", (2880, 900), record_crm=True)
    fail_set(wf, "Fail: Conflict Unresolved", "HUBSPOT_CONFLICT_UNRESOLVED", "={{ true }}",
             "Contact existant non identifiable : la prochaine tentative le retrouvera par recherche", (3120, 900), record_crm=True)
    fail_set(wf, "Fail: Record Error", http_status_code("RECORD_HTTP_"), RETRYABLE_HTTP, "Résultat CRM non enregistré", (3600, 420), record_crm=False)
    wf.node("Failure Info", "n8n-nodes-base.noOp", 1, {}, (3360, 900))
    wf.if_node("Record CRM State?", [("={{ $json.fail_record_crm }}", "boolean:true", None)], (3600, 900))
    wf.http("Record CRM Failure", "POST", url(f"'/leads/' + {EV}.lead_id + '/crm-sync'"), (3840, 840),
            body=json_body("{ event_id: " + EV + ".event_id, provider: " + CTX + ".provider, "
                           "status: $('Failure Info').first().json.fail_retryable ? 'RETRYING' : 'FAILED', "
                           "error_code: $('Failure Info').first().json.fail_error_code }"),
            headers=backend_headers("crm-failure"), credentials=CRED_API,
            notes="Rend l'état CRM visible dans le dashboard (RETRYING / FAILED) avant de rapporter l'échec.")
    failure_tail(wf, "Failure Info", 4080, 900)

    # câblage
    wf.connect("LF Config", "Get CRM Context")
    wf.connect("Get CRM Context", "Context OK?")
    wf.connect("Context OK?", "Route By CRM_PROVIDER", 0)
    wf.connect("Context OK?", "Fail: Context Error", 1)
    wf.connect("Route By CRM_PROVIDER", "Mock CRM Upsert", 0)
    wf.connect("Route By CRM_PROVIDER", "Known External ID?", 1)
    wf.connect("Route By CRM_PROVIDER", "Fail: Unknown Provider", 2)
    wf.connect("Mock CRM Upsert", "Mock Upsert OK?")
    wf.connect("Mock Upsert OK?", "Prepare Sync Result (mock)", 0)
    wf.connect("Mock Upsert OK?", "Fail: Mock CRM Error", 1)
    wf.connect("Prepare Sync Result (mock)", "Record CRM Sync")
    wf.connect("Known External ID?", "Prepare Update (known id)", 0)
    wf.connect("Known External ID?", "HubSpot: Search Contact", 1)
    wf.connect("Prepare Update (known id)", "HubSpot: Update Contact")
    wf.connect("HubSpot: Search Contact", "Classify Search")
    wf.connect("Classify Search", "Prepare Update (from search)", 0)
    wf.connect("Classify Search", "HubSpot: Create Contact", 1)
    wf.connect("Classify Search", "Fail: Rate Limited", 2)
    wf.connect("Classify Search", "Fail: Auth Error", 3)
    wf.connect("Classify Search", "Fail: Transient", 4)
    wf.connect("Classify Search", "Fail: Client Error", 5)
    wf.connect("Prepare Update (from search)", "HubSpot: Update Contact")
    wf.connect("HubSpot: Update Contact", "Classify Update")
    wf.connect("Classify Update", "Prepare Result (hubspot update)", 0)
    wf.connect("Classify Update", "Fail: Rate Limited", 1)
    wf.connect("Classify Update", "Fail: Auth Error", 2)
    wf.connect("Classify Update", "Fail: Transient", 3)
    wf.connect("Classify Update", "Fail: Client Error", 4)
    wf.connect("HubSpot: Create Contact", "Classify Create")
    wf.connect("Classify Create", "Prepare Result (hubspot create)", 0)
    wf.connect("Classify Create", "Reconcile Existing Contact", 1)
    wf.connect("Classify Create", "Fail: Rate Limited", 2)
    wf.connect("Classify Create", "Fail: Auth Error", 3)
    wf.connect("Classify Create", "Fail: Transient", 4)
    wf.connect("Classify Create", "Fail: Client Error", 5)
    wf.connect("Reconcile Existing Contact", "Reconciled?")
    wf.connect("Reconciled?", "HubSpot: Update Contact", 0)
    wf.connect("Reconciled?", "Fail: Conflict Unresolved", 1)
    wf.connect("Prepare Result (hubspot update)", "Record CRM Sync")
    wf.connect("Prepare Result (hubspot create)", "Record CRM Sync")
    wf.connect("Record CRM Sync", "Sync Recorded?")
    wf.connect("Sync Recorded?", "Complete Event", 0)
    wf.connect("Sync Recorded?", "Fail: Record Error", 1)
    for f in ("Fail: Context Error", "Fail: Unknown Provider", "Fail: Mock CRM Error", "Fail: Rate Limited", "Fail: Auth Error",
              "Fail: Transient", "Fail: Client Error", "Fail: Conflict Unresolved", "Fail: Record Error"):
        wf.connect(f, "Failure Info")
    wf.connect("Failure Info", "Record CRM State?")
    wf.connect("Record CRM State?", "Record CRM Failure", 0)
    wf.connect("Record CRM State?", "Report Failure", 1)
    wf.connect("Record CRM Failure", "Report Failure")
    wf.note("**LF-WF-02 — CRM.** Le mode (mock | hubspot) vient du backend (`CRM_PROVIDER`). Mode hubspot : recherche par e-mail → "
            "mise à jour OU création ; 409 « déjà existant » → réconciliation ; 429/401/403/5xx/timeout → /fail (retry décidé par le backend). "
            "Credential HubSpot requis UNIQUEMENT en mode hubspot (Private App, scope crm.objects.contacts.read/write).",
            (0, 40), (520, 190), 7)
    return wf


# ---------------------------------------------------------------------------------------------------
# WF-03 — Follow-up Draft Generator
# ---------------------------------------------------------------------------------------------------
def wf03() -> Workflow:
    wf = Workflow("LF-WF-03 Followup Draft",
                  "Événement DRAFT_REQUESTED -> rédaction OpenAI (via FastAPI) -> contrôle -> brouillon DRAFT. AUCUN envoi d'e-mail.")
    child_preamble(wf, "lf-wf-03-followup-draft")

    wf.http("Get Draft Context", "GET", url(f"'/leads/' + {EV}.lead_id + '/draft-context'"), (720, 300),
            headers=backend_headers(idempotent=False), credentials=CRED_API)
    wf.if_node("Context OK?", [("={{ $json.statusCode }}", "number:equals", 200)], (960, 300))
    wf.if_node("Draft Already Open?", [("={{ $json.body.has_open_draft }}", "boolean:true", None)], (1200, 240))
    wf.http("Generate Draft", "POST", url(f"'/leads/' + {EV}.lead_id + '/draft/generate'"), (1440, 300),
            body=json_body("{ event_id: " + EV + ".event_id }"), headers=backend_headers("draft-gen"), credentials=CRED_API,
            timeout=110000, notes="FastAPI appelle OpenAI (ou le mock) puis applique la politique : pas de prix, délai, engagement ou lien inventé.")
    wf.switch_node("Classify Generation", [
        ("generated", [("={{ $json.statusCode }}", "number:equals", 200), ("={{ $json.body.ok }}", "boolean:true", None)]),
        ("policy_rejected", [("={{ $json.statusCode }}", "number:equals", 200), ("={{ $json.body.ok }}", "boolean:false", None)]),
        ("transient", [("={{ !$json.statusCode || $json.statusCode >= 500 }}", "boolean:true", None)]),
    ], (1680, 300))
    wf.if_node("Validate Draft Content", [
        ("={{ $json.body.draft.subject }}", "string:notEmpty", None),
        ("={{ $json.body.draft.body }}", "string:notEmpty", None),
        ("={{ $json.body.draft.body.length }}", "number:lte", 3000),
        ("={{ /https?:\\/\\/|www\\./i.test($json.body.draft.body) }}", "boolean:false", None),
    ], (1920, 180))
    wf.http("Create Draft", "POST", url(f"'/leads/' + {EV}.lead_id + '/followups'"), (2160, 120),
            body=json_body("{ event_id: " + EV + ".event_id, draft: $('Generate Draft').first().json.body.draft, "
                           "provider: $('Generate Draft').first().json.body.provider, "
                           "model_name: $('Generate Draft').first().json.body.model, "
                           "prompt_version: $('Generate Draft').first().json.body.prompt_version }"),
            headers=backend_headers("draft-create"), credentials=CRED_API,
            notes="Crée le brouillon avec le statut DRAFT. Il n'existe aucun nœud d'envoi d'e-mail dans ce workflow.")
    wf.if_node("Draft Created?", [("={{ [200, 201].includes($json.statusCode) }}", "boolean:true", None)], (2400, 120))
    complete_node(wf, "Complete Event", "SUCCEEDED", (2640, 60), "LF-WF-03")
    wf.node("Stop: Awaiting Human Review", "n8n-nodes-base.noOp", 1, {}, (2880, 60),
            notes="Fin du workflow. L'approbation se fait dans le dashboard et n'envoie AUCUN e-mail (MVP).")
    wf.if_node("Create Rejected By Policy?", [("={{ $json.statusCode }}", "number:equals", 422)], (2640, 220))
    complete_node(wf, "Complete (manual review)", "MANUAL_REVIEW", (2880, 400), "LF-WF-03", "draft_policy_violation")

    fail_set(wf, "Fail: Context Error", http_status_code("DRAFT_CONTEXT_HTTP_"), RETRYABLE_HTTP, "Contexte du brouillon illisible", (960, 560))
    fail_set(wf, "Fail: LLM Transient", "={{ $json.body?.error?.code || 'LLM_NO_RESPONSE' }}",
             "={{ $json.body?.error?.details?.retryable ?? true }}", "Service IA indisponible", (1680, 560))
    fail_set(wf, "Fail: Generation Rejected", http_status_code("DRAFT_HTTP_"), "={{ false }}", "Génération refusée par le backend", (1680, 680))
    fail_set(wf, "Fail: Create Error", http_status_code("FOLLOWUP_HTTP_"), RETRYABLE_HTTP, "Création du brouillon impossible", (2880, 240))
    wf.node("Failure Info", "n8n-nodes-base.noOp", 1, {}, (3120, 600))
    failure_tail(wf, "Failure Info", 3360, 600)

    wf.connect("LF Config", "Get Draft Context")
    wf.connect("Get Draft Context", "Context OK?")
    wf.connect("Context OK?", "Draft Already Open?", 0)
    wf.connect("Context OK?", "Fail: Context Error", 1)
    wf.connect("Draft Already Open?", "Complete Event", 0)
    wf.connect("Draft Already Open?", "Generate Draft", 1)
    wf.connect("Generate Draft", "Classify Generation")
    wf.connect("Classify Generation", "Validate Draft Content", 0)
    wf.connect("Classify Generation", "Complete (manual review)", 1)
    wf.connect("Classify Generation", "Fail: LLM Transient", 2)
    wf.connect("Classify Generation", "Fail: Generation Rejected", 3)
    wf.connect("Validate Draft Content", "Create Draft", 0)
    wf.connect("Validate Draft Content", "Complete (manual review)", 1)
    wf.connect("Create Draft", "Draft Created?")
    wf.connect("Draft Created?", "Complete Event", 0)
    wf.connect("Draft Created?", "Create Rejected By Policy?", 1)
    wf.connect("Complete Event", "Stop: Awaiting Human Review")
    wf.connect("Create Rejected By Policy?", "Complete (manual review)", 0)
    wf.connect("Create Rejected By Policy?", "Fail: Create Error", 1)
    for f in ("Fail: Context Error", "Fail: LLM Transient", "Fail: Generation Rejected", "Fail: Create Error"):
        wf.connect(f, "Failure Info")
    wf.connect("Failure Info", "Report Failure")
    wf.note("**LF-WF-03 — Brouillon.** Contexte → génération (FastAPI→OpenAI) → contrôle de contenu → POST /followups (statut DRAFT) → STOP. "
            "Aucun nœud « Send Email » : l'envoi d'e-mail n'existe pas dans le MVP.", (0, 40), (460, 150), 7)
    return wf


# ---------------------------------------------------------------------------------------------------
# WF-04 — Operations & Recovery
# ---------------------------------------------------------------------------------------------------
def wf04() -> Workflow:
    wf = Workflow("LF-WF-04 Operations Recovery",
                  "Planification : réserve les événements outbox prêts (lease) et les route vers WF-01/02/03. Reprise après crash.")
    wf.node("Schedule Trigger (recovery poll)", "n8n-nodes-base.scheduleTrigger", 1.2,
            {"rule": {"interval": [{"field": "minutes", "minutesInterval": POLL_MINUTES}]}}, (0, 220),
            notes=f"Filet de récupération toutes les {POLL_MINUTES} min (réglable : voir README, `--poll-minutes`, ou éditer ce nœud). "
                  "Le déclenchement normal est le webhook « Wake » appelé par le backend après chaque soumission. "
                  "Le backend Render peut dormir : le premier appel le réveille (timeout 90 s).")
    wf.node("Wake Webhook (best-effort, from backend)", "n8n-nodes-base.webhook", 2,
            {"httpMethod": "POST", "path": "lf-wf-04-wake", "authentication": "headerAuth", "responseMode": "onReceived",
             "options": {}}, (0, 380), credentials=CRED_WEBHOOK_HEADER, webhook=True,
            notes="Appelé par FastAPI après l'enregistrement d'une demande (au mieux). Ne transporte aucune donnée métier : "
                  "il déclenche seulement une réservation d'événements. Sa perte est sans conséquence (le poll de récupération reprend).")
    wf.node("Manual Trigger", "n8n-nodes-base.manualTrigger", 1, {}, (0, 540), notes="Lancement manuel pour tester / reprendre immédiatement.")
    wf.set_node("LF Config", {
        "api_base_url": API_PLACEHOLDER,
        "n8n_base_url": N8N_PLACEHOLDER,
        "claim_limit": (5, "number"),
        "worker_name": "n8n-ovh",
    }, (240, 380))
    wf.note("**À MODIFIER après import** : `api_base_url` (API FastAPI + /api/v1/internal) et `n8n_base_url` (URL de CETTE instance n8n, "
            "ex. http://localhost:5678 si WF-04 appelle ses propres webhooks en local). Voir IMPORT_GUIDE.md.", (200, 220), (400, 120), 3)

    wf.http("Claim Events", "POST", url("'/outbox/claim'"), (480, 380),
            body=json_body("{ limit: $('LF Config').first().json.claim_limit, worker: $('LF Config').first().json.worker_name }"),
            headers={"X-LF-Timestamp": "={{ Date.now() }}"}, credentials=CRED_API, timeout=90000,
            notes="Réservation atomique (SKIP LOCKED) avec lease. Les événements dont la lease a expiré (crash) sont repris automatiquement.")
    wf.if_node("Claim OK?", [("={{ $json.statusCode }}", "number:equals", 200)], (720, 380))
    wf.node("Backend Unreachable (next run retries)", "n8n-nodes-base.noOp", 1, {}, (960, 560),
            notes="Aucune action : l'outbox est persistante, la prochaine exécution réessaiera.")
    wf.node("Split Events", "n8n-nodes-base.splitOut", 1, {"fieldToSplitOut": "body.events", "options": {}}, (960, 300))
    wf.switch_node("Route By Event Type", [
        ("LEAD_SUBMITTED", [("={{ $json.event_type }}", "string:equals", "LEAD_SUBMITTED")]),
        ("CRM_SYNC_REQUESTED", [("={{ $json.event_type }}", "string:equals", "CRM_SYNC_REQUESTED")]),
        ("DRAFT_REQUESTED", [("={{ $json.event_type }}", "string:equals", "DRAFT_REQUESTED")]),
    ], (1200, 300))

    def dispatch(name: str, path: str, y: int) -> None:
        wf.http(name, "POST", "={{ $('LF Config').first().json.n8n_base_url + '/webhook/" + path + "' }}", (1440, y),
                body="={{ JSON.stringify($('Split Events').item.json) }}", credentials=CRED_WEBHOOK_HEADER, timeout=20000,
                notes="Appel du workflow enfant (accusé 202 immédiat). Le workflow enfant rapporte lui-même complete/fail au backend.")

    dispatch("Dispatch LF-WF-01", "lf-wf-01-lead-qualification", 160)
    dispatch("Dispatch LF-WF-02", "lf-wf-02-crm-sync", 300)
    dispatch("Dispatch LF-WF-03", "lf-wf-03-followup-draft", 440)
    wf.if_node("Dispatch Accepted?", [("={{ $json.statusCode >= 200 && $json.statusCode < 300 }}", "boolean:true", None)], (1680, 300))
    wf.node("Dispatched", "n8n-nodes-base.noOp", 1, {}, (1920, 240))
    wf.http("Report Dispatch Failure", "POST", url("'/outbox/' + $('Split Events').item.json.event_id + '/fail'"), (1920, 380),
            body=json_body("{ attempt: $('Split Events').item.json.attempt, error_code: 'N8N_DISPATCH_FAILED', retryable: true, "
                           "message: 'Workflow enfant injoignable ou inactif (HTTP ' + ($json.statusCode || 'timeout') + ')' }"),
            headers={"X-LF-Timestamp": "={{ Date.now() }}",
                     "X-Correlation-ID": "={{ $('Split Events').item.json.correlation_id }}",
                     "Idempotency-Key": "={{ $('Split Events').item.json.event_id + ':' + $('Split Events').item.json.attempt + ':dispatch-fail' }}"},
            credentials=CRED_API, notes="Le backend planifie le retry (backoff) ou la dead-letter ; aucun second système de retry dans n8n.")
    wf.http("Report Unknown Event Type", "POST", url("'/outbox/' + $json.event_id + '/fail'"), (1440, 620),
            body=json_body("{ attempt: $json.attempt, error_code: 'UNKNOWN_EVENT_TYPE', retryable: false, message: $json.event_type }"),
            headers={"X-LF-Timestamp": "={{ Date.now() }}", "X-Correlation-ID": "={{ $json.correlation_id }}",
                     "Idempotency-Key": "={{ $json.event_id + ':' + $json.attempt + ':unknown-type' }}"}, credentials=CRED_API)

    # branche d'alerte : Error Trigger (à désigner comme "Error workflow" des WF-01/02/03)
    wf.node("Error Trigger", "n8n-nodes-base.errorTrigger", 1, {}, (0, 800),
            notes="Désigner ce workflow comme « Error workflow » dans les réglages de LF-WF-01/02/03.")
    wf.set_node("Format Alert", {
        "alert_workflow": "={{ $json.workflow.name }}",
        "alert_execution_id": "={{ $json.execution.id }}",
        "alert_node": "={{ $json.execution.lastNodeExecuted }}",
        "alert_message": "={{ $json.execution.error.message }}",
    }, (240, 800))
    wf.node("Alert Placeholder (connect Slack / e-mail interne)", "n8n-nodes-base.noOp", 1, {}, (480, 800),
            notes="Brancher ici une notification INTERNE (jamais un e-mail commercial). Le backend reste la source de vérité des états.")

    wf.connect("Schedule Trigger (recovery poll)", "LF Config")
    wf.connect("Wake Webhook (best-effort, from backend)", "LF Config")
    wf.connect("Manual Trigger", "LF Config")
    wf.chain("LF Config", "Claim Events", "Claim OK?")
    wf.connect("Claim OK?", "Split Events", 0)
    wf.connect("Claim OK?", "Backend Unreachable (next run retries)", 1)
    wf.connect("Split Events", "Route By Event Type")
    wf.connect("Route By Event Type", "Dispatch LF-WF-01", 0)
    wf.connect("Route By Event Type", "Dispatch LF-WF-02", 1)
    wf.connect("Route By Event Type", "Dispatch LF-WF-03", 2)
    wf.connect("Route By Event Type", "Report Unknown Event Type", 3)
    for d in ("Dispatch LF-WF-01", "Dispatch LF-WF-02", "Dispatch LF-WF-03"):
        wf.connect(d, "Dispatch Accepted?")
    wf.connect("Dispatch Accepted?", "Dispatched", 0)
    wf.connect("Dispatch Accepted?", "Report Dispatch Failure", 1)
    wf.chain("Error Trigger", "Format Alert", "Alert Placeholder (connect Slack / e-mail interne)")
    wf.note("**LF-WF-04 — Opérations.** Planifié : réserve les événements prêts (lease) → route vers WF-01/02/03 → enregistre les erreurs. "
            "Le backend est l'unique autorité des tentatives (backoff, max, dead-letter). Reprise manuelle : bouton du dashboard "
            "(« Reprise manuelle ») puis prochaine exécution, ou lancer ce workflow à la main.", (0, 40), (520, 150), 7)
    return wf


def main() -> None:
    global POLL_MINUTES
    if "--poll-minutes" in sys.argv:
        POLL_MINUTES = int(sys.argv[sys.argv.index("--poll-minutes") + 1])
        if not 1 <= POLL_MINUTES <= 720:
            raise SystemExit("--poll-minutes doit être compris entre 1 et 720")
    for fn, filename in ((wf01, "WF-01-Lead-Qualification.json"), (wf02, "WF-02-HubSpot-CRM-Sync.json"),
                         (wf03, "WF-03-Followup-Draft.json"), (wf04, "WF-04-Operations-Recovery.json")):
        path = fn().write(OUT, filename)
        print(f"écrit {path.relative_to(OUT.parents[1])}")


if __name__ == "__main__":
    main()
