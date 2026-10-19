"""Énumérations métier et catalogue de services (source unique pour backend, scoring, prompts)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LeadStatus(StrEnum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    QUALIFIED = "QUALIFIED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    READY = "READY"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class Segment(StrEnum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class CrmSyncStatus(StrEnum):
    PENDING = "PENDING"
    SYNCED = "SYNCED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"


class FollowupStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    # Réservés à la V2 : aucun code du MVP ne produit ces valeurs.
    READY_TO_SEND = "READY_TO_SEND"
    SENT = "SENT"
    FAILED = "FAILED"


class RunStatus(StrEnum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class OutboxStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    RETRYING = "RETRYING"
    DEAD_LETTER = "DEAD_LETTER"


class EventType(StrEnum):
    """Événements portés par l'outbox (actionnables par n8n)."""

    LEAD_SUBMITTED = "LEAD_SUBMITTED"
    CRM_SYNC_REQUESTED = "CRM_SYNC_REQUESTED"
    DRAFT_REQUESTED = "DRAFT_REQUESTED"


# Événement outbox -> workflow n8n responsable.
EVENT_WORKFLOW = {
    EventType.LEAD_SUBMITTED: "LF-WF-01-Lead-Qualification",
    EventType.CRM_SYNC_REQUESTED: "LF-WF-02-HubSpot-CRM-Sync",
    EventType.DRAFT_REQUESTED: "LF-WF-03-Followup-Draft",
}


class Role(StrEnum):
    ADMIN = "ADMIN"
    SALES = "SALES"


class ActorType(StrEnum):
    SYSTEM = "system"
    USER = "user"
    SERVICE = "service"


SCORING_RULE_VERSION = "scoring-v1"


@dataclass(frozen=True)
class ServiceDefinition:
    id: str
    label_fr: str
    label_en: str
    min_budget_eur: int


# Catalogue fictif de l'agence NovaDigital. Les budgets minimums servent uniquement au scoring.
SERVICE_CATALOG: dict[str, ServiceDefinition] = {
    s.id: s
    for s in [
        ServiceDefinition("web_development", "Création de site web", "Website development", 2500),
        ServiceDefinition("workflow_automation", "Automatisation de processus", "Workflow automation", 1500),
        ServiceDefinition(
            "customer_support_automation", "Automatisation du support client", "Customer support automation", 2000
        ),
        ServiceDefinition("ai_integration", "Intégration d'IA", "AI integration", 3000),
        ServiceDefinition("data_dashboard", "Tableaux de bord de données", "Data dashboards", 2000),
    ]
}
KNOWN_SERVICE_IDS: tuple[str, ...] = tuple(SERVICE_CATALOG)
REQUESTABLE_SERVICES: tuple[str, ...] = (*KNOWN_SERVICE_IDS, "other")

INTENTS: tuple[str, ...] = (
    "automation",
    "web_development",
    "ai_solution",
    "data_analytics",
    "consulting",
    "other",
    "unknown",
)
NEED_CLARITY: tuple[str, ...] = ("clear", "partial", "unclear", "unknown")
LANGUAGES: tuple[str, ...] = ("fr", "en", "es", "de", "it", "pt", "other", "unknown")

SHORT_TIMELINE_DAYS = 30
HOT_THRESHOLD = 75
WARM_THRESHOLD = 45
