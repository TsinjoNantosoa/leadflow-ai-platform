"""Qualifications, CRM, brouillons, runs, outbox, audit, idempotence, usage LLM."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import CrmSyncStatus, FollowupStatus, OutboxStatus, RunStatus, Segment
from app.database.base import Base, created_at_col, sql_in, updated_at_col, uuid_pk  # noqa: F401

JSON_EMPTY = text("'{}'::jsonb")
JSON_EMPTY_ARRAY = text("'[]'::jsonb")


class Qualification(Base):
    __tablename__ = "qualifications"
    __table_args__ = (
        UniqueConstraint("lead_id", "version"),
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint(sql_in("segment", Segment), name="segment"),
        CheckConstraint(
            "(segment = 'HOT' AND score >= 75) OR (segment = 'WARM' AND score >= 45 AND score < 75)"
            " OR (segment = 'COLD' AND score < 45)",
            name="segment_matches_score",
        ),
        CheckConstraint("budget_amount IS NULL OR budget_amount >= 0", name="budget_non_negative"),
        CheckConstraint("timeline_days IS NULL OR timeline_days >= 0", name="timeline_non_negative"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    service: Mapped[str | None] = mapped_column(String(64))
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    timeline_days: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(8))
    summary: Mapped[str | None] = mapped_column(Text)
    need_clarity: Mapped[str | None] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    segment: Mapped[str] = mapped_column(String(8), nullable=False)
    score_explanation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_EMPTY)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_EMPTY)
    llm_provider: Mapped[str | None] = mapped_column(String(16))
    model_name: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    scoring_rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    review_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=JSON_EMPTY_ARRAY)
    created_at: Mapped[datetime] = created_at_col()


class CrmMapping(Base):
    __tablename__ = "crm_mappings"
    __table_args__ = (
        UniqueConstraint("organization_id", "contact_id", "provider", name="uq_crm_org_contact_provider"),
        UniqueConstraint("organization_id", "provider", "external_contact_id", name="uq_crm_org_provider_external"),
        CheckConstraint(sql_in("sync_status", CrmSyncStatus), name="sync_status"),
        CheckConstraint("provider IN ('mock','hubspot')", name="provider"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    external_contact_id: Mapped[str | None] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", server_default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class MockCrmContact(Base):
    """CRM factice (CRM_PROVIDER=mock) : simule la recherche/création idempotente d'un contact."""

    __tablename__ = "mock_crm_contacts"
    __table_args__ = (UniqueConstraint("organization_id", "email_normalized"),)

    external_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_EMPTY)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Followup(Base):
    __tablename__ = "followups"
    __table_args__ = (
        CheckConstraint(sql_in("status", FollowupStatus), name="status"),
        # Garantie structurelle du MVP : aucun brouillon ne peut passer à READY_TO_SEND / SENT.
        CheckConstraint(
            "status NOT IN ('READY_TO_SEND','SENT') AND sent_at IS NULL", name="no_send_in_mvp"
        ),
        CheckConstraint("char_length(subject) BETWEEN 1 AND 200", name="subject_length"),
        CheckConstraint("char_length(body) BETWEEN 1 AND 6000", name="body_length"),
        Index("ix_followups_lead", "lead_id"),
        Index("ix_followups_status", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), nullable=False)
    qualification_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("qualifications.id"))
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="email", server_default="email")
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    creation_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    llm_provider: Mapped[str | None] = mapped_column(String(16))
    model_name: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    edited_by: Mapped[str | None] = mapped_column(Text)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[str | None] = mapped_column(Text)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint(sql_in("status", OutboxStatus), name="status"),
        CheckConstraint("attempt_count >= 0 AND max_attempts >= 1", name="attempts_positive"),
        Index("ix_outbox_due", "status", "next_attempt_at"),
        Index("ix_outbox_lease", "status", "locked_until"),
        Index("ix_outbox_lead", "lead_id"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, default=uuid.uuid4)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_EMPTY)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", server_default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(64))
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        CheckConstraint(sql_in("status", RunStatus), name="status"),
        UniqueConstraint("outbox_event_id", "attempt_count", name="uq_runs_event_attempt"),
        Index("ix_runs_corr", "correlation_id"),
        Index("ix_runs_lead", "lead_id"),
        Index("ix_runs_started", "started_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("outbox_events.id"))
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="STARTED", server_default="STARTED")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=JSON_EMPTY)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('system','user','service')", name="actor_type"),
        Index("ix_audit_org_created", "organization_id", "created_at"),
        Index("ix_audit_lead_created", "lead_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_ref: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, server_default=JSON_EMPTY)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = created_at_col()


class IdempotencyRecord(Base):
    """Rejeu sûr des mutations internes : même clé + même empreinte => même réponse."""

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    scope: Mapped[str] = mapped_column(String(96), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_col()


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    __table_args__ = (Index("ix_llm_usage_created", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # extraction | draft
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = created_at_col()


__all__ = [
    "AuditEvent",
    "AutomationRun",
    "CrmMapping",
    "Followup",
    "IdempotencyRecord",
    "LlmUsage",
    "MockCrmContact",
    "OutboxEvent",
    "Qualification",
]
