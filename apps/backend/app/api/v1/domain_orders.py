from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, Domain, DomainOrder, DomainStatus, User
from app.services.billing import entitlement_decision

router = APIRouter(tags=["domain-orders"])

OPEN_STATUSES = {"pending", "processing"}
ALLOWED_OPERATIONS = {"register", "renew", "transfer_in"}
OWNER_STATUSES = {"pending", "processing", "completed", "failed", "canceled"}
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def _normalize_domain(value: str) -> str:
    raw = value.strip().lower().rstrip(".")
    if not raw or "://" in raw or "/" in raw or "@" in raw or any(ch.isspace() for ch in raw):
        raise ValueError("Enter only a domain name, for example example.co.ls")
    try:
        ascii_name = raw.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Domain name is invalid") from exc
    if not DOMAIN_RE.fullmatch(ascii_name):
        raise ValueError("Domain name is invalid")
    return ascii_name


class DomainOrderCreate(BaseModel):
    domain_name: str = Field(min_length=4, max_length=253)
    operation: str = "register"
    years: int = Field(default=1, ge=1, le=10)

    @field_validator("domain_name")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return _normalize_domain(value)

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in ALLOWED_OPERATIONS:
            raise ValueError("operation must be register, renew or transfer_in")
        return normalized


class OwnerDomainOrderPatch(BaseModel):
    status: str
    provider: str | None = Field(default=None, max_length=40)
    provider_order_id: str | None = Field(default=None, max_length=120)
    response: dict | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in OWNER_STATUSES:
            raise ValueError("Unsupported domain order status")
        return normalized


def _out(row: DomainOrder) -> dict:
    response = None
    if row.response_json:
        try:
            response = json.loads(row.response_json)
        except json.JSONDecodeError:
            response = {"message": row.response_json}
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "domain_name": row.domain_name,
        "operation": row.operation,
        "years": row.years,
        "provider": row.provider,
        "provider_order_id": row.provider_order_id,
        "status": row.status,
        "response": response,
        "created_by_user_id": str(row.created_by_user_id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _audit(db: Session, tenant_id: UUID, current: User, action: str, row: DomainOrder, metadata: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=current.id,
        action=action,
        resource_type="domain_order",
        resource_id=str(row.id),
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


@router.get("/tenants/{tenant_id}/domain-orders")
def list_domain_orders(
    tenant_id: UUID,
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.read", db, current)
    rows = db.scalars(
        select(DomainOrder)
        .where(DomainOrder.tenant_id == tenant_id)
        .order_by(DomainOrder.created_at.desc())
        .limit(limit)
    ).all()
    return {"items": [_out(row) for row in rows], "total": len(rows), "registrar_automation": False}


@router.post("/tenants/{tenant_id}/domain-orders", status_code=201)
def create_domain_order(
    tenant_id: UUID,
    payload: DomainOrderCreate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    domain_name = payload.domain_name

    duplicate = db.scalar(select(DomainOrder).where(
        DomainOrder.tenant_id == tenant_id,
        DomainOrder.domain_name == domain_name,
        DomainOrder.operation == payload.operation,
        DomainOrder.status.in_(OPEN_STATUSES),
    ))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="An open order already exists for this domain and operation")

    managed_domain = db.scalar(select(Domain).where(
        Domain.tenant_id == tenant_id,
        Domain.ascii_name == domain_name,
        Domain.status != DomainStatus.archived,
    ))

    if payload.operation == "renew" and managed_domain is None:
        raise HTTPException(status_code=409, detail="Renewal requires the domain to already be managed by this organization")

    if payload.operation in {"register", "transfer_in"} and managed_domain is None:
        decision = entitlement_decision(db, tenant_id, "domain")
        if not decision.get("allowed"):
            raise HTTPException(status_code=409, detail=str(decision.get("reason") or "Domain package limit reached"))

    row = DomainOrder(
        tenant_id=tenant_id,
        domain_name=domain_name,
        operation=payload.operation,
        years=payload.years,
        provider="manual",
        status="pending",
        response_json=json.dumps({
            "message": "Order accepted by Ithute. External registrar automation is not configured yet; fulfillment remains pending until processed by the platform owner.",
            "registrar_automation": False,
        }),
        created_by_user_id=current.id,
    )
    db.add(row)
    db.flush()
    _audit(db, tenant_id, current, "domain.order.create", row, {"operation": row.operation, "domain": row.domain_name, "years": row.years})
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/tenants/{tenant_id}/domain-orders/{order_id}/cancel")
def cancel_domain_order(
    tenant_id: UUID,
    order_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "dns.manage", db, current)
    row = db.get(DomainOrder, order_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Domain order not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending domain orders can be canceled by the customer")
    row.status = "canceled"
    row.response_json = json.dumps({"message": "Canceled by customer", "canceled_at": datetime.now(timezone.utc).isoformat()})
    _audit(db, tenant_id, current, "domain.order.cancel", row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/platform/domain-orders")
def list_platform_domain_orders(
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    query = select(DomainOrder)
    if status:
        query = query.where(DomainOrder.status == status.strip().lower())
    rows = db.scalars(query.order_by(DomainOrder.created_at.desc()).limit(limit)).all()
    return {"items": [_out(row) for row in rows], "total": len(rows), "registrar_automation": False}


@router.patch("/platform/domain-orders/{order_id}")
def update_platform_domain_order(
    order_id: UUID,
    payload: OwnerDomainOrderPatch,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    row = db.get(DomainOrder, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Domain order not found")
    if row.status in {"completed", "canceled"} and payload.status not in {row.status}:
        raise HTTPException(status_code=409, detail="Completed or canceled domain orders cannot be reopened")
    row.status = payload.status
    if payload.provider is not None:
        row.provider = payload.provider.strip().lower() or "manual"
    if payload.provider_order_id is not None:
        row.provider_order_id = payload.provider_order_id.strip() or None
    if payload.response is not None:
        row.response_json = json.dumps(payload.response, sort_keys=True)
    _audit(db, row.tenant_id, current, "domain.order.status", row, {"status": row.status, "provider": row.provider})
    db.commit()
    db.refresh(row)
    return _out(row)
