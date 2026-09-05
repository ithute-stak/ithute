from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.db.session import get_db
from app.models import DmarcAggregateReport, MailAutomationRule, MailRetentionPolicy, PhishingFinding, User

router = APIRouter(prefix="/mail-intelligence", tags=["mail-intelligence"])

class RetentionPolicyIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    retention_days: int = Field(default=2555, ge=1, le=36500)
    legal_hold: bool = False
    immutable_archive: bool = True
    mailbox_scope: list[str] = Field(default_factory=list, max_length=10000)

class DmarcReportIn(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    report_id: str = Field(min_length=1, max_length=255)
    reporter: str | None = Field(default=None, max_length=255)
    period_begin: datetime
    period_end: datetime
    total_messages: int = Field(default=0, ge=0)
    aligned_messages: int = Field(default=0, ge=0)
    failed_messages: int = Field(default=0, ge=0)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    raw_summary: dict[str, Any] = Field(default_factory=dict)

class PhishingFindingIn(BaseModel):
    mailbox_id: uuid.UUID | None = None
    message_ref: str = Field(min_length=1, max_length=512)
    severity: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    finding_type: str = Field(min_length=2, max_length=120)
    sender: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=500)
    indicators: list[dict[str, Any] | str] = Field(default_factory=list)
    action_taken: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)

class AutomationRuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    enabled: bool = True
    trigger_event: str = Field(default="mail.received", pattern=r"^[a-z0-9][a-z0-9_.-]{1,159}$")
    conditions: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list, max_length=50)

def _require(tenant_id: uuid.UUID, permission: str, db: Session, current: User) -> None:
    require_tenant_permission(tenant_id, permission, db, current)

@router.get("/tenants/{tenant_id}/overview")
def overview(tenant_id: uuid.UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict[str, Any]:
    _require(tenant_id, "mail.read", db, current)
    latest = db.scalar(select(DmarcAggregateReport).where(DmarcAggregateReport.tenant_id == tenant_id).order_by(DmarcAggregateReport.period_end.desc()).limit(1))
    return {
        "retention_policies": db.scalar(select(func.count()).select_from(MailRetentionPolicy).where(MailRetentionPolicy.tenant_id == tenant_id)) or 0,
        "legal_holds": db.scalar(select(func.count()).select_from(MailRetentionPolicy).where(MailRetentionPolicy.tenant_id == tenant_id, MailRetentionPolicy.legal_hold.is_(True))) or 0,
        "phishing_open": db.scalar(select(func.count()).select_from(PhishingFinding).where(PhishingFinding.tenant_id == tenant_id, PhishingFinding.resolved.is_(False))) or 0,
        "automations_enabled": db.scalar(select(func.count()).select_from(MailAutomationRule).where(MailAutomationRule.tenant_id == tenant_id, MailAutomationRule.enabled.is_(True))) or 0,
        "latest_dmarc": ({"domain": latest.domain, "period_end": latest.period_end.isoformat(), "total_messages": latest.total_messages, "aligned_messages": latest.aligned_messages, "failed_messages": latest.failed_messages, "alignment_rate": round((latest.aligned_messages / latest.total_messages) * 100, 2) if latest.total_messages else 0} if latest else None),
    }

@router.get("/tenants/{tenant_id}/retention")
def list_retention(tenant_id: uuid.UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    _require(tenant_id, "mail.read", db, current)
    return [{"id": str(item.id), "name": item.name, "retention_days": item.retention_days, "legal_hold": item.legal_hold, "immutable_archive": item.immutable_archive, "mailbox_scope": item.mailbox_scope_json, "created_at": item.created_at.isoformat()} for item in db.scalars(select(MailRetentionPolicy).where(MailRetentionPolicy.tenant_id == tenant_id).order_by(MailRetentionPolicy.name))]

@router.post("/tenants/{tenant_id}/retention", status_code=201)
def create_retention(tenant_id: uuid.UUID, payload: RetentionPolicyIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict[str, Any]:
    _require(tenant_id, "mail.manage", db, current)
    item = MailRetentionPolicy(tenant_id=tenant_id, name=payload.name, retention_days=payload.retention_days, legal_hold=payload.legal_hold, immutable_archive=payload.immutable_archive, mailbox_scope_json=payload.mailbox_scope, created_by=current.id)
    db.add(item)
    try: db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail="Retention policy name already exists") from exc
    return {"id": str(item.id), "created": True}

@router.post("/tenants/{tenant_id}/retention/{policy_id}/legal-hold")
def legal_hold(tenant_id: uuid.UUID, policy_id: uuid.UUID, enabled: bool = True, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict[str, Any]:
    _require(tenant_id, "mail.manage", db, current)
    item = db.get(MailRetentionPolicy, policy_id)
    if item is None or item.tenant_id != tenant_id: raise HTTPException(status_code=404, detail="Retention policy not found")
    item.legal_hold = enabled; db.commit(); return {"id": str(item.id), "legal_hold": item.legal_hold}

@router.get("/tenants/{tenant_id}/dmarc")
def dmarc_reports(tenant_id: uuid.UUID, domain: str | None = Query(default=None, max_length=255), limit: int = Query(default=90, ge=1, le=500), db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    _require(tenant_id, "mail.read", db, current)
    query = select(DmarcAggregateReport).where(DmarcAggregateReport.tenant_id == tenant_id)
    if domain: query = query.where(DmarcAggregateReport.domain == domain.lower())
    return [{"id": str(item.id), "domain": item.domain, "report_id": item.report_id, "reporter": item.reporter, "period_begin": item.period_begin.isoformat(), "period_end": item.period_end.isoformat(), "total_messages": item.total_messages, "aligned_messages": item.aligned_messages, "failed_messages": item.failed_messages, "alignment_rate": round((item.aligned_messages / item.total_messages) * 100, 2) if item.total_messages else 0, "sources": item.sources_json} for item in db.scalars(query.order_by(DmarcAggregateReport.period_end.desc()).limit(limit))]

@router.post("/tenants/{tenant_id}/dmarc", status_code=202)
def ingest_dmarc(tenant_id: uuid.UUID, payload: DmarcReportIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict[str, Any]:
    _require(tenant_id, "mail.manage", db, current)
    item = DmarcAggregateReport(tenant_id=tenant_id, domain=payload.domain.lower(), report_id=payload.report_id, reporter=payload.reporter, period_begin=payload.period_begin, period_end=payload.period_end, total_messages=payload.total_messages, aligned_messages=payload.aligned_messages, failed_messages=payload.failed_messages, sources_json=payload.sources, raw_summary_json=payload.raw_summary)
    db.add(item)
    try: db.commit()
    except IntegrityError:
        db.rollback(); existing = db.scalar(select(DmarcAggregateReport).where(DmarcAggregateReport.tenant_id == tenant_id, DmarcAggregateReport.report_id == payload.report_id)); return {"accepted": True, "duplicate": True, "id": str(existing.id) if existing else None}
    return {"accepted": True, "duplicate": False, "id": str(item.id)}

@router.get("/tenants/{tenant_id}/phishing")
def phishing_findings(tenant_id: uuid.UUID, resolved: bool | None = None, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    _require(tenant_id, "mail.read", db, current)
    query = select(PhishingFinding).where(PhishingFinding.tenant_id == tenant_id)
    if resolved is not None: query = query.where(PhishingFinding.resolved == resolved)
    return [{"id": str(item.id), "mailbox_id": str(item.mailbox_id) if item.mailbox_id else None, "message_ref": item.message_ref, "severity": item.severity, "finding_type": item.finding_type, "sender": item.sender, "subject": item.subject, "indicators": item.indicators_json, "action_taken": item.action_taken, "resolved": item.resolved, "metadata": item.metadata_json, "created_at": item.created_at.isoformat()} for item in db.scalars(query.order_by(PhishingFinding.created_at.desc()).limit(limit))]

@router.post("/tenants/{tenant_id}/phishing", status_code=202)
def ingest_phishing(tenant_id: uuid.UUID, payload: PhishingFindingIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict[str, Any]:
    _require(tenant_id, "mail.manage", db, current)
    item = PhishingFinding(tenant_id=tenant_id, mailbox_id=payload.mailbox_id, message_ref=payload.message_ref, severity=payload.severity, finding_type=payload.finding_type, sender=payload.sender, subject=payload.subject, indicators_json=payload.indicators, action_taken=payload.action_taken, metadata_json=payload.metadata)
    db.add(item); db.commit(); return {"accepted": True, "id": str(item.id)}

@router.post("/tenants/{tenant_id}/phishing/{finding_id}/resolve")
def resolve_phishing(tenant_id: uuid.UUID, finding_id: uuid.UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict[str, Any]:
    _require(tenant_id, "mail.manage", db, current)
    item = db.get(PhishingFinding, finding_id)
    if item is None or item.tenant_id != tenant_id: raise HTTPException(status_code=404, detail="Finding not found")
    item.resolved = True; item.resolved_at = datetime.now().astimezone(); db.commit(); return {"id": str(item.id), "resolved": True}

@router.get("/tenants/{tenant_id}/automations")
def automations(tenant_id: uuid.UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> list[dict[str, Any]]:
    _require(tenant_id, "mail.read", db, current)
    return [{"id": str(item.id), "name": item.name, "enabled": item.enabled, "trigger_event": item.trigger_event, "conditions": item.conditions_json, "actions": item.actions_json, "run_count": item.run_count, "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None, "last_error": item.last_error} for item in db.scalars(select(MailAutomationRule).where(MailAutomationRule.tenant_id == tenant_id).order_by(MailAutomationRule.name))]

@router.post("/tenants/{tenant_id}/automations", status_code=201)
def create_automation(tenant_id: uuid.UUID, payload: AutomationRuleIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)) -> dict[str, Any]:
    _require(tenant_id, "mail.manage", db, current)
    item = MailAutomationRule(tenant_id=tenant_id, name=payload.name, enabled=payload.enabled, trigger_event=payload.trigger_event, conditions_json=payload.conditions, actions_json=payload.actions, created_by=current.id)
    db.add(item)
    try: db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(status_code=409, detail="Automation name already exists") from exc
    return {"id": str(item.id), "created": True}
