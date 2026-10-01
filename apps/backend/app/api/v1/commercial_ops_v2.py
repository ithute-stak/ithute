from __future__ import annotations

from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from socket import getaddrinfo
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, User
from app.models.commercial_ops_v2 import BillingContract, UptimeCheck, UptimeMonitor
from app.services.commercial_ops_v2 import get_or_create_contract, run_billing_cycle

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
