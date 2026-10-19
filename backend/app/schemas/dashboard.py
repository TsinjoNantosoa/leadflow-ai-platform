"""Schémas de réponse du dashboard (documentés dans OpenAPI)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    role: str


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)


class LeadListItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    status: str
    status_reason: str | None
    full_name: str
    email: str
    company: str | None
    requested_service: str | None
    service: str | None
    score: int | None
    segment: str | None
    human_review_required: bool
    crm_status: str | None
    followup_status: str | None
    is_demo: bool


class ContactOut(ORM):
    id: uuid.UUID
    full_name: str
    email: str
    company: str | None
    phone: str | None
    consent_status: str
    lead_count: int = 0


class QualificationOut(ORM):
    id: uuid.UUID
    version: int
    intent: str
    service: str | None
    budget_amount: Decimal | None
    budget_currency: str | None
    timeline_days: int | None
    language: str | None
    summary: str | None
    need_clarity: str | None
    score: int
    segment: str
    score_explanation: dict[str, Any]
    extracted_data: dict[str, Any]
    llm_provider: str | None
    model_name: str | None
    prompt_version: str | None
    scoring_rule_version: str
    human_review_required: bool
    review_reasons: list[str]
    created_at: datetime


class CrmOut(BaseModel):
    provider: str
    external_contact_id: str | None
    sync_status: str
    attempt_count: int
    last_error_code: str | None
    last_synced_at: datetime | None


class FollowupOut(ORM):
    id: uuid.UUID
    lead_id: uuid.UUID
    channel: str
    subject: str
    body: str
    language: str | None
    status: str
    edit_version: int
    model_name: str | None
    prompt_version: str | None
    llm_provider: str | None
    edited_by: str | None
    edited_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    rejected_by: str | None
    rejected_at: datetime | None
    reject_reason: str | None
    created_at: datetime
    updated_at: datetime
    is_demo: bool


class FollowupReviewItem(FollowupOut):
    lead_full_name: str
    lead_company: str | None
    lead_score: int | None
    lead_segment: str | None


class RunOut(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID | None
    outbox_event_id: uuid.UUID | None
    correlation_id: uuid.UUID
    workflow_name: str
    event_type: str | None
    status: str
    attempt_count: int
    max_attempts: int | None
    error_code: str | None
    error_message: str | None
    duration_ms: int | None
    started_at: datetime
    finished_at: datetime | None
    event_status: str | None
    next_attempt_at: datetime | None
    can_retry: bool
    is_demo: bool


class AuditOut(BaseModel):
    id: uuid.UUID
    action: str
    actor_type: str
    actor_ref: str | None
    metadata: dict[str, Any]
    created_at: datetime


class TimelineStep(BaseModel):
    key: str
    label: str
    state: str  # done | pending | failed | skipped | attention
    at: datetime | None
    detail: str | None = None


class LeadDetail(BaseModel):
    id: uuid.UUID
    created_at: datetime
    status: str
    status_reason: str | None
    source: str
    requested_service: str | None
    message: str
    is_demo: bool
    privacy_notice_version: str | None
    contact: ContactOut
    qualification: QualificationOut | None
    qualification_history: list[dict[str, Any]]
    crm: CrmOut | None
    followups: list[FollowupOut]
    runs: list[RunOut]
    audit: list[AuditOut]
    timeline: list[TimelineStep]


class FollowupPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str | None = Field(None, min_length=3, max_length=200)
    body: str | None = Field(None, min_length=20, max_length=6000)
    expected_version: int | None = None


class FollowupDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int | None = None
    reason: str | None = Field(None, max_length=500)
