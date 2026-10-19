"""Requêtes de lecture du dashboard : listes, détail, supervision, métriques. Tout est calculé depuis PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, or_, select, text, true
from sqlalchemy.orm import Session

from app.core.constants import FollowupStatus, LeadStatus, OutboxStatus
from app.core.errors import ApiError
from app.models import (
    AuditEvent,
    AutomationRun,
    Contact,
    CrmMapping,
    Followup,
    Lead,
    LlmUsage,
    OutboxEvent,
    Qualification,
)
from app.schemas.dashboard import (
    AuditOut,
    ContactOut,
    CrmOut,
    FollowupOut,
    FollowupReviewItem,
    LeadDetail,
    LeadListItem,
    QualificationOut,
    RunOut,
)
from app.services.timeline import build_timeline


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- Leads ----------------------------------------------------------------------------------------
def list_leads(db: Session, org_id: uuid.UUID, *, status: str | None, segment: str | None, service: str | None,
               q: str | None, review: bool | None, page: int, page_size: int, sort: str, order: str) -> dict[str, Any]:
    lq = (
        select(Qualification.score.label("score"), Qualification.segment.label("segment"),
               Qualification.service.label("service"), Qualification.human_review_required.label("review"))
        .where(Qualification.lead_id == Lead.id)
        .order_by(Qualification.version.desc())
        .limit(1)
        .lateral("lq")
    )
    lf = (
        select(Followup.status.label("fstatus"))
        .where(Followup.lead_id == Lead.id)
        .order_by(Followup.created_at.desc())
        .limit(1)
        .lateral("lf")
    )
    lc = (
        select(CrmMapping.sync_status.label("cstatus"))
        .where(CrmMapping.contact_id == Lead.contact_id)
        .order_by(CrmMapping.updated_at.desc())
        .limit(1)
        .lateral("lc")
    )
    base = (
        select(Lead, Contact, lq.c.score, lq.c.segment, lq.c.service, lq.c.review, lf.c.fstatus, lc.c.cstatus)
        .join(Contact, and_(Contact.id == Lead.contact_id))
        .outerjoin(lq, true())
        .outerjoin(lf, true())
        .outerjoin(lc, true())
        .where(Lead.organization_id == org_id)
    )
    if status:
        base = base.where(Lead.status == status)
    if segment:
        base = base.where(lq.c.segment == segment)
    if service:
        base = base.where(or_(lq.c.service == service, and_(lq.c.service.is_(None), Lead.requested_service == service)))
    if review is not None:
        base = base.where(func.coalesce(lq.c.review, False) == review)
    if q:
        like = f"%{_escape_like(q.strip())}%"
        base = base.where(or_(Contact.full_name.ilike(like, escape="\\"), Contact.email.ilike(like, escape="\\"),
                              Contact.company.ilike(like, escape="\\")))
    total = db.execute(select(func.count()).select_from(base.order_by(None).subquery())).scalar_one()

    sort_col = {"score": lq.c.score, "created_at": Lead.created_at, "status": Lead.status,
                "name": Contact.full_name}.get(sort, Lead.created_at)
    ordering = sort_col.asc().nulls_last() if order == "asc" else sort_col.desc().nulls_last()
    rows = db.execute(base.order_by(ordering, Lead.id).limit(page_size).offset((page - 1) * page_size)).all()
    items = [
        LeadListItem(
            id=lead.id, created_at=lead.created_at, status=lead.status, status_reason=lead.status_reason,
            full_name=contact.full_name, email=contact.email, company=contact.company,
            requested_service=lead.requested_service, service=svc, score=score, segment=seg,
            human_review_required=bool(rev), crm_status=cstatus, followup_status=fstatus, is_demo=lead.is_demo,
        )
        for lead, contact, score, seg, svc, rev, fstatus, cstatus in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _run_out(run: AutomationRun, ev: OutboxEvent | None) -> RunOut:
    can_retry = bool(
        ev and ev.status in (OutboxStatus.DEAD_LETTER.value, OutboxStatus.RETRYING.value)
        and run.attempt_count == ev.attempt_count
    )
    return RunOut(
        id=run.id, lead_id=run.lead_id, outbox_event_id=run.outbox_event_id, correlation_id=run.correlation_id,
        workflow_name=run.workflow_name, event_type=run.event_type, status=run.status, attempt_count=run.attempt_count,
        max_attempts=ev.max_attempts if ev else None, error_code=run.error_code, error_message=run.error_message,
        duration_ms=run.duration_ms, started_at=run.started_at, finished_at=run.finished_at,
        event_status=ev.status if ev else None, next_attempt_at=ev.next_attempt_at if ev else None,
        can_retry=can_retry, is_demo=run.is_demo,
    )


def lead_detail(db: Session, org_id: uuid.UUID, lead_id: uuid.UUID) -> LeadDetail:
    lead = db.execute(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id)).scalar_one_or_none()
    if lead is None:
        raise ApiError(404, "lead_not_found", "Lead introuvable")
    contact = db.get(Contact, lead.contact_id)
    lead_count = db.execute(select(func.count()).select_from(Lead).where(Lead.contact_id == contact.id)).scalar_one()
    quals = db.execute(select(Qualification).where(Qualification.lead_id == lead.id)
                       .order_by(Qualification.version.desc())).scalars().all()
    mapping = db.execute(select(CrmMapping).where(CrmMapping.contact_id == contact.id)
                         .order_by(CrmMapping.updated_at.desc()).limit(1)).scalar_one_or_none()
    followups = db.execute(select(Followup).where(Followup.lead_id == lead.id).order_by(Followup.created_at.desc())
                           ).scalars().all()
    run_rows = db.execute(
        select(AutomationRun, OutboxEvent).outerjoin(OutboxEvent, OutboxEvent.id == AutomationRun.outbox_event_id)
        .where(AutomationRun.lead_id == lead.id).order_by(AutomationRun.started_at.desc())
    ).all()
    audits = db.execute(select(AuditEvent).where(AuditEvent.lead_id == lead.id)
                        .order_by(AuditEvent.created_at.desc()).limit(200)).scalars().all()

    return LeadDetail(
        id=lead.id, created_at=lead.created_at, status=lead.status, status_reason=lead.status_reason,
        source=lead.source, requested_service=lead.requested_service, message=lead.message, is_demo=lead.is_demo,
        privacy_notice_version=lead.privacy_notice_version,
        contact=ContactOut(id=contact.id, full_name=contact.full_name, email=contact.email, company=contact.company,
                           phone=contact.phone, consent_status=contact.consent_status, lead_count=lead_count),
        qualification=QualificationOut.model_validate(quals[0]) if quals else None,
        qualification_history=[
            {"version": q.version, "score": q.score, "segment": q.segment, "created_at": q.created_at.isoformat(),
             "human_review_required": q.human_review_required} for q in quals
        ],
        crm=None if mapping is None else CrmOut(
            provider=mapping.provider, external_contact_id=mapping.external_contact_id,
            sync_status=mapping.sync_status, attempt_count=mapping.attempt_count,
            last_error_code=mapping.last_error_code, last_synced_at=mapping.last_synced_at),
        followups=[FollowupOut.model_validate(f) for f in followups],
        runs=[_run_out(r, e) for r, e in run_rows],
        audit=[AuditOut(id=a.id, action=a.action, actor_type=a.actor_type, actor_ref=a.actor_ref,
                        metadata=a.event_metadata, created_at=a.created_at) for a in audits],
        timeline=build_timeline(lead, quals, mapping, followups, audits),
    )


# --- Brouillons ----------------------------------------------------------------------------------
def list_followups(db: Session, org_id: uuid.UUID, *, status: str | None, page: int, page_size: int) -> dict[str, Any]:
    lq = (
        select(Qualification.score.label("score"), Qualification.segment.label("segment"))
        .where(Qualification.lead_id == Lead.id).order_by(Qualification.version.desc()).limit(1).lateral("lq")
    )
    base = (
        select(Followup, Contact, lq.c.score, lq.c.segment)
        .join(Lead, Lead.id == Followup.lead_id).join(Contact, Contact.id == Lead.contact_id)
        .outerjoin(lq, true()).where(Lead.organization_id == org_id)
    )
    if status:
        base = base.where(Followup.status == status)
    total = db.execute(select(func.count()).select_from(base.order_by(None).subquery())).scalar_one()
    # DRAFT d'abord (à traiter), puis les décisions les plus récentes.
    order = case((Followup.status == FollowupStatus.DRAFT.value, 0), else_=1)
    rows = db.execute(base.order_by(order, Followup.created_at.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    items = [
        FollowupReviewItem(**FollowupOut.model_validate(f).model_dump(), lead_full_name=c.full_name,
                           lead_company=c.company, lead_score=score, lead_segment=seg)
        for f, c, score, seg in rows
    ]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def followup_history(db: Session, org_id: uuid.UUID, followup_id: uuid.UUID) -> list[AuditOut]:
    f = db.get(Followup, followup_id)
    lead = db.get(Lead, f.lead_id) if f else None
    if f is None or lead is None or lead.organization_id != org_id:
        raise ApiError(404, "followup_not_found", "Brouillon introuvable")
    rows = db.execute(
        select(AuditEvent).where(AuditEvent.lead_id == lead.id, AuditEvent.action.like("draft.%"),
                                 AuditEvent.event_metadata["followup_id"].astext == str(followup_id))
        .order_by(AuditEvent.created_at.desc())
    ).scalars().all()
    return [AuditOut(id=a.id, action=a.action, actor_type=a.actor_type, actor_ref=a.actor_ref,
                     metadata=a.event_metadata, created_at=a.created_at) for a in rows]


# --- Runs ----------------------------------------------------------------------------------------
def list_runs(db: Session, org_id: uuid.UUID, *, lead_id: uuid.UUID | None, status: str | None, workflow: str | None,
              page: int, page_size: int) -> dict[str, Any]:
    base = (
        select(AutomationRun, OutboxEvent)
        .outerjoin(OutboxEvent, OutboxEvent.id == AutomationRun.outbox_event_id)
        .outerjoin(Lead, Lead.id == AutomationRun.lead_id)
        .where(or_(Lead.organization_id == org_id, AutomationRun.lead_id.is_(None)))
    )
    if lead_id:
        base = base.where(AutomationRun.lead_id == lead_id)
    if status:
        base = base.where(AutomationRun.status == status)
    if workflow:
        base = base.where(AutomationRun.workflow_name == workflow)
    total = db.execute(select(func.count()).select_from(base.order_by(None).subquery())).scalar_one()
    rows = db.execute(base.order_by(AutomationRun.started_at.desc()).limit(page_size).offset((page - 1) * page_size)).all()
    return {"items": [_run_out(r, e) for r, e in rows], "total": total, "page": page, "page_size": page_size}


# --- Métriques -----------------------------------------------------------------------------------
def overview(db: Session, org_id: uuid.UUID, days: int = 14) -> dict[str, Any]:
    status_counts = dict(db.execute(
        select(Lead.status, func.count()).where(Lead.organization_id == org_id).group_by(Lead.status)).all())
    total = sum(status_counts.values())
    demo = db.execute(select(func.count()).select_from(Lead).where(Lead.organization_id == org_id,
                                                                   Lead.is_demo.is_(True))).scalar_one()

    seg_rows = db.execute(text("""
        SELECT segment, count(*) FROM (
          SELECT DISTINCT ON (q.lead_id) q.segment FROM qualifications q
          JOIN leads l ON l.id = q.lead_id WHERE l.organization_id = :org ORDER BY q.lead_id, q.version DESC
        ) t GROUP BY segment"""), {"org": org_id}).all()
    segments = {"HOT": 0, "WARM": 0, "COLD": 0, **{s: c for s, c in seg_rows}}

    since = datetime.now(UTC).date() - timedelta(days=days - 1)
    series_rows = db.execute(text("""
        SELECT d::date AS day, count(l.id) FROM generate_series(CAST(:since AS date), CURRENT_DATE, interval '1 day') d
        LEFT JOIN leads l ON l.organization_id = :org AND (l.created_at AT TIME ZONE 'UTC')::date = d::date
        GROUP BY d ORDER BY d"""), {"since": since, "org": org_id}).all()

    run_rows = db.execute(
        select(AutomationRun.workflow_name, AutomationRun.status, func.count())
        .outerjoin(Lead, Lead.id == AutomationRun.lead_id)
        .where(or_(Lead.organization_id == org_id, AutomationRun.lead_id.is_(None)),
               AutomationRun.started_at >= datetime.now(UTC) - timedelta(days=7))
        .group_by(AutomationRun.workflow_name, AutomationRun.status)).all()
    runs: dict[str, dict[str, int]] = {}
    for wf, st, c in run_rows:
        runs.setdefault(wf, {})[st] = c

    outbox_counts = dict(db.execute(
        select(OutboxEvent.status, func.count()).where(OutboxEvent.organization_id == org_id)
        .group_by(OutboxEvent.status)).all())
    draft_counts = dict(db.execute(
        select(Followup.status, func.count()).join(Lead, Lead.id == Followup.lead_id)
        .where(Lead.organization_id == org_id).group_by(Followup.status)).all())
    crm_counts = dict(db.execute(
        select(CrmMapping.sync_status, func.count()).where(CrmMapping.organization_id == org_id)
        .group_by(CrmMapping.sync_status)).all())

    lat = db.execute(text("""
        SELECT count(*) n,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY secs) p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY secs) p95
        FROM (SELECT extract(epoch FROM (q.created_at - l.created_at)) secs
              FROM qualifications q JOIN leads l ON l.id = q.lead_id
              WHERE l.organization_id = :org AND q.version = 1 AND NOT l.is_demo) t"""), {"org": org_id}).one()

    llm = db.execute(
        select(func.count(), func.coalesce(func.sum(LlmUsage.input_tokens), 0),
               func.coalesce(func.sum(LlmUsage.output_tokens), 0), func.sum(LlmUsage.estimated_cost_usd))
        .where(LlmUsage.provider != "mock")).one()

    recent = db.execute(
        select(AuditEvent, Contact.full_name).outerjoin(Lead, Lead.id == AuditEvent.lead_id)
        .outerjoin(Contact, Contact.id == Lead.contact_id)
        .where(AuditEvent.organization_id == org_id, AuditEvent.lead_id.is_not(None))  # activité liée aux leads
        .order_by(AuditEvent.created_at.desc()).limit(12)).all()

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "data_origin": {"total_leads": total, "demo_leads": demo, "real_leads": total - demo},
        "leads": {
            "received": total,
            "qualified": status_counts.get(LeadStatus.QUALIFIED.value, 0) + status_counts.get(LeadStatus.READY.value, 0),
            "manual_review": status_counts.get(LeadStatus.MANUAL_REVIEW.value, 0),
            "failed": status_counts.get(LeadStatus.FAILED.value, 0),
            "in_progress": status_counts.get(LeadStatus.NEW.value, 0) + status_counts.get(LeadStatus.PROCESSING.value, 0),
            "by_status": status_counts,
        },
        "segments": segments,
        "series": [{"date": d.isoformat(), "count": c} for d, c in series_rows],
        "runs_last_7_days": runs,
        "outbox": outbox_counts,
        "drafts": draft_counts,
        "crm": crm_counts,
        "qualification_latency_seconds": {
            "samples": lat.n, "p50": float(lat.p50) if lat.p50 is not None else None,
            "p95": float(lat.p95) if lat.p95 is not None else None, "scope": "leads non démo, première qualification",
        },
        "llm_usage": {"calls": llm[0], "input_tokens": int(llm[1]), "output_tokens": int(llm[2]),
                      "estimated_cost_usd": float(llm[3]) if llm[3] is not None else None, "scope": "appels non mock"},
        "recent_activity": [
            {"id": str(a.id), "action": a.action, "actor_type": a.actor_type, "lead_id": str(a.lead_id) if a.lead_id else None,
             "lead_name": name, "created_at": a.created_at.isoformat(), "is_demo": a.is_demo} for a, name in recent
        ],
    }
