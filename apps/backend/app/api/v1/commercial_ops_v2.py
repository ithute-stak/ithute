from __future__ import annotations

from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from socket import getaddrinfo
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, BillingPlan, SubscriptionStatus, TenantAddon, TenantSubscription, User
from app.models.commercial_ops_v2 import BillingContract, UptimeCheck, UptimeMonitor
from app.services.commercial_ops_v2 import get_or_create_contract, request_plan_change, run_billing_cycle

router = APIRouter(tags=["commercial-ops-v2"])


class ContractPatch(BaseModel):
    billing_interval: str | None = None
    auto_renew: bool | None = None
    invoice_lead_days: int | None = Field(default=None, ge=0, le=60)
    grace_days: int | None = Field(default=None, ge=0, le=60)
    discount_percent: int | None = Field(default=None, ge=0, le=100)
    credit_balance_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)

    @field_validator("billing_interval")
    @classmethod
    def validate_interval(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"monthly", "annual"}:
            raise ValueError("billing_interval must be monthly or annual")
        return normalized


class LifecyclePatch(BaseModel):
    state: str

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"sellable", "hidden", "legacy", "archived"}:
            raise ValueError("state must be sellable, hidden, legacy or archived")
        return normalized


class MonitorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    url: str = Field(min_length=8, max_length=500)
    interval_minutes: int = Field(default=5, ge=1, le=1440)
    expected_status: int = Field(default=200, ge=100, le=599)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Monitor URL must be a public HTTPS URL without embedded credentials")
        try:
            infos = getaddrinfo(parsed.hostname, parsed.port or 443, type=1)
        except OSError as exc:
            raise ValueError("Monitor hostname does not currently resolve") from exc
        addresses = {item[4][0] for item in infos}
        if not addresses or any(not ip_address(addr).is_global for addr in addresses):
            raise ValueError("Monitor target must resolve only to public internet addresses")
        return value.strip()


class MonitorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    interval_minutes: int | None = Field(default=None, ge=1, le=1440)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    enabled: bool | None = None


def _contract_out(row: BillingContract) -> dict:
    return {
        "id": str(row.id), "tenant_id": str(row.tenant_id), "billing_interval": row.billing_interval,
        "auto_renew": row.auto_renew, "invoice_lead_days": row.invoice_lead_days, "grace_days": row.grace_days,
        "discount_percent": row.discount_percent, "credit_balance_minor": row.credit_balance_minor,
        "setup_fee_applied": row.setup_fee_applied,
        "next_invoice_at": row.next_invoice_at.isoformat() if row.next_invoice_at else None,
    }


def _monitor_out(row: UptimeMonitor) -> dict:
    return {
        "id": str(row.id), "tenant_id": str(row.tenant_id), "name": row.name, "url": row.url,
        "interval_minutes": row.interval_minutes, "expected_status": row.expected_status, "enabled": row.enabled,
        "last_status": row.last_status, "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
        "last_response_ms": row.last_response_ms, "last_http_status": row.last_http_status, "last_error": row.last_error,
    }


def _subscriber_count(db: Session, plan_id: UUID) -> int:
    return int(db.scalar(select(func.count(TenantSubscription.id)).where(
        or_(TenantSubscription.plan_id == plan_id, TenantSubscription.base_plan_id == plan_id),
        TenantSubscription.status.in_([SubscriptionStatus.trialing, SubscriptionStatus.active, SubscriptionStatus.past_due]),
    )) or 0)


@router.get("/platform/commercial/package-lifecycle")
def package_lifecycle(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    rows = db.scalars(select(BillingPlan).where(~BillingPlan.code.like("effective-%")).order_by(BillingPlan.sort_order, BillingPlan.name)).all()
    return {"items": [{
        "id": str(plan.id),
        "code": plan.code,
        "name": plan.name,
        "state": plan.lifecycle_state,
        "customer_visible": plan.customer_visible,
        "is_active": plan.is_active,
        "subscriber_count": _subscriber_count(db, plan.id),
        "retired_at": plan.retired_at.isoformat() if plan.retired_at else None,
    } for plan in rows]}


@router.post("/platform/commercial/package-lifecycle/{plan_id}")
def set_package_lifecycle(plan_id: UUID, payload: LifecyclePatch, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    plan = db.get(BillingPlan, plan_id)
    if plan is None or plan.code.startswith("effective-"):
        raise HTTPException(404, "Package not found")
    subscribers = _subscriber_count(db, plan.id)
    if payload.state == "archived" and subscribers:
        raise HTTPException(409, f"Package has {subscribers} active subscriber(s); mark it legacy instead of archiving it")

    plan.lifecycle_state = payload.state
    if payload.state == "sellable":
        plan.customer_visible = True
        plan.is_active = True
        plan.retired_at = None
    elif payload.state in {"hidden", "legacy"}:
        plan.customer_visible = False
        plan.is_active = True
        plan.retired_at = None
    else:
        plan.customer_visible = False
        plan.is_active = False
        plan.featured = False
        plan.retired_at = datetime.now(timezone.utc)

    db.add(AuditLog(actor_user_id=current.id, action="billing.plan.lifecycle", resource_type="billing_plan", resource_id=str(plan.id), metadata_json=f'{{"state":"{payload.state}"}}'))
    db.commit(); db.refresh(plan)
    return {"id": str(plan.id), "state": plan.lifecycle_state, "subscriber_count": subscribers, "customer_visible": plan.customer_visible, "is_active": plan.is_active}


@router.post("/tenants/{tenant_id}/commercial/change-plan/{plan_id}")
def change_plan(tenant_id: UUID, plan_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
    if subscription is None:
        raise HTTPException(404, "Subscription not found")
    target = db.get(BillingPlan, plan_id)
    if target is None:
        raise HTTPException(404, "Target package not found")
    try:
        result = request_plan_change(db, subscription, target)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="billing.plan.change", resource_type="tenant_subscription", resource_id=str(subscription.id), metadata_json=f'{{"target_plan":"{target.code}","mode":"{result["mode"]}"}}'))
    db.commit()
    return {"target_plan": target.code, **result}


@router.post("/tenants/{tenant_id}/commercial/addons/{assignment_id}/cancel-at-period-end")
def cancel_addon_at_period_end(tenant_id: UUID, assignment_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    row = db.get(TenantAddon, assignment_id)
    if row is None or row.tenant_id != tenant_id or row.status != "active":
        raise HTTPException(404, "Active add-on assignment not found")
    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
    if subscription is None:
        raise HTTPException(409, "Subscription not found")
    row.cancel_at_period_end = True
    row.current_period_end = subscription.current_period_end
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="billing.addon.cancel_at_period_end", resource_type="tenant_addon", resource_id=str(row.id)))
    db.commit(); db.refresh(row)
    return {"assignment_id": str(row.id), "cancel_at_period_end": True, "effective_at": row.current_period_end.isoformat() if row.current_period_end else None}


@router.get("/tenants/{tenant_id}/commercial/contract")
def get_contract(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.read", db, current)
    row = get_or_create_contract(db, tenant_id)
    db.commit(); db.refresh(row)
    return _contract_out(row)


@router.patch("/tenants/{tenant_id}/commercial/contract")
def update_contract(tenant_id: UUID, payload: ContractPatch, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = get_or_create_contract(db, tenant_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(row, key, value)
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="commercial.contract.update", resource_type="billing_contract", resource_id=str(row.id)))
    db.commit(); db.refresh(row)
    return _contract_out(row)


@router.post("/platform/commercial/run-billing-cycle")
def run_cycle(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    result = run_billing_cycle(db)
    db.add(AuditLog(actor_user_id=current.id, action="commercial.billing_cycle.run", resource_type="billing_cycle", resource_id=datetime.now(timezone.utc).isoformat()))
    db.commit()
    return result


@router.get("/tenants/{tenant_id}/monitoring/monitors")
def list_monitors(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    rows = db.scalars(select(UptimeMonitor).where(UptimeMonitor.tenant_id == tenant_id).order_by(UptimeMonitor.created_at.desc())).all()
    return {"items": [_monitor_out(row) for row in rows]}


@router.post("/tenants/{tenant_id}/monitoring/monitors", status_code=201)
def create_monitor(tenant_id: UUID, payload: MonitorCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = UptimeMonitor(tenant_id=tenant_id, name=payload.name.strip(), url=payload.url, interval_minutes=payload.interval_minutes, expected_status=payload.expected_status)
    db.add(row); db.flush()
    db.add(AuditLog(tenant_id=tenant_id, actor_user_id=current.id, action="monitor.create", resource_type="uptime_monitor", resource_id=str(row.id)))
    db.commit(); db.refresh(row)
    return _monitor_out(row)


@router.patch("/tenants/{tenant_id}/monitoring/monitors/{monitor_id}")
def update_monitor(tenant_id: UUID, monitor_id: UUID, payload: MonitorPatch, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.manage", db, current)
    row = db.get(UptimeMonitor, monitor_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(404, "Monitor not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit(); db.refresh(row)
    return _monitor_out(row)


@router.get("/tenants/{tenant_id}/monitoring/sla")
def sla_summary(tenant_id: UUID, days: int = Query(default=30, ge=1, le=365), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "hosting.read", db, current)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    monitor_ids = select(UptimeMonitor.id).where(UptimeMonitor.tenant_id == tenant_id)
    total = db.scalar(select(func.count(UptimeCheck.id)).where(UptimeCheck.monitor_id.in_(monitor_ids), UptimeCheck.checked_at >= since)) or 0
    up = db.scalar(select(func.count(UptimeCheck.id)).where(UptimeCheck.monitor_id.in_(monitor_ids), UptimeCheck.checked_at >= since, UptimeCheck.status == "up")) or 0
    avg_ms = db.scalar(select(func.avg(UptimeCheck.response_ms)).where(UptimeCheck.monitor_id.in_(monitor_ids), UptimeCheck.checked_at >= since, UptimeCheck.response_ms.is_not(None)))
    uptime = round((up / total) * 100, 4) if total else None
    return {"days": days, "checks": int(total), "successful_checks": int(up), "uptime_percent": uptime, "average_response_ms": round(float(avg_ms), 2) if avg_ms is not None else None}
