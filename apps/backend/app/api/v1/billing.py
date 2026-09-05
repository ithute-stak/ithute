import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.core.config import settings
from app.db.session import get_db
from app.models import AuditLog, BillingInvoice, BillingPlan, SubscriptionStatus, Tenant, User
from app.services.billing import (
    assign_subscription,
    billing_summary,
    capture_usage,
    ensure_default_plans,
    entitlement_decision,
    generate_invoice,
    invoice_out,
    process_payment_event,
    verify_webhook_signature,
)

router = APIRouter(tags=["billing"])


class SubscriptionAssign(BaseModel):
    plan_code: str = Field(min_length=2, max_length=50)
    status: SubscriptionStatus = SubscriptionStatus.active
    period_days: int = Field(default=30, ge=1, le=366)


class InvoiceGenerate(BaseModel):
    due_days: int = Field(default=14, ge=0, le=90)


def _plan_out(plan: BillingPlan) -> dict:
    return {
        "id": str(plan.id),
        "code": plan.code,
        "name": plan.name,
        "currency": plan.currency,
        "monthly_price_minor": plan.monthly_price_minor,
        "included_mailboxes": plan.included_mailboxes,
        "included_domains": plan.included_domains,
        "included_storage_mb": plan.included_storage_mb,
        "max_api_keys": plan.max_api_keys,
        "is_active": plan.is_active,
    }


def _audit(db: Session, tenant_id: UUID, current: User, action: str, resource_type: str, resource_id: str, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_user_id=current.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


@router.get("/billing/plans")
def list_plans(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_default_plans(db)
    plans = db.scalars(select(BillingPlan).where(BillingPlan.is_active.is_(True)).order_by(BillingPlan.monthly_price_minor)).all()
    return {"items": [_plan_out(plan) for plan in plans]}


@router.get("/tenants/{tenant_id}/billing/summary")
def tenant_billing_summary(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.read", db, current)
    return billing_summary(db, tenant_id)


@router.get("/tenants/{tenant_id}/billing/entitlements/{resource}")
def tenant_entitlement(
    tenant_id: UUID,
    resource: str,
    requested_storage_bytes: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "billing.read", db, current)
    try:
        return entitlement_decision(db, tenant_id, resource, requested_storage_bytes=requested_storage_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/tenants/{tenant_id}/billing/usage/snapshot", status_code=201)
def snapshot_tenant_usage(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    snapshot = capture_usage(db, tenant_id)
    _audit(
        db,
        tenant_id,
        current,
        "billing.usage.snapshot",
        "usage_snapshot",
        str(snapshot.id),
        {"mailboxes": snapshot.mailboxes, "domains": snapshot.domains},
    )
    db.commit()
    return {
        "id": str(snapshot.id),
        "mailboxes": snapshot.mailboxes,
        "domains": snapshot.domains,
        "storage_bytes": snapshot.storage_bytes,
        "period_start": snapshot.period_start.isoformat() if snapshot.period_start else None,
        "period_end": snapshot.period_end.isoformat() if snapshot.period_end else None,
        "captured_at": snapshot.captured_at.isoformat(),
    }


@router.put("/tenants/{tenant_id}/billing/subscription")
def set_subscription(
    tenant_id: UUID,
    payload: SubscriptionAssign,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    ensure_default_plans(db)
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == payload.plan_code.lower(), BillingPlan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status_code=404, detail="Billing plan not found")
    subscription = assign_subscription(db, tenant_id, plan, payload.status, payload.period_days)
    _audit(
        db,
        tenant_id,
        current,
        "billing.subscription.assign",
        "tenant_subscription",
        str(subscription.id),
        {"plan_code": plan.code, "status": subscription.status.value},
    )
    db.commit()
    return billing_summary(db, tenant_id)


@router.get("/tenants/{tenant_id}/billing/invoices")
def list_invoices(
    tenant_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "billing.read", db, current)
    items = db.scalars(
        select(BillingInvoice)
        .where(BillingInvoice.tenant_id == tenant_id)
        .order_by(BillingInvoice.created_at.desc())
        .limit(limit)
    ).all()
    return {"items": [invoice_out(item) for item in items], "total": len(items)}


@router.post("/tenants/{tenant_id}/billing/invoices", status_code=201)
def create_invoice(
    tenant_id: UUID,
    payload: InvoiceGenerate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    try:
        invoice = generate_invoice(db, tenant_id, due_days=payload.due_days)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _audit(
        db,
        tenant_id,
        current,
        "billing.invoice.generate",
        "billing_invoice",
        str(invoice.id),
        {"invoice_number": invoice.invoice_number, "total_minor": invoice.total_minor, "currency": invoice.currency},
    )
    db.commit()
    return invoice_out(invoice)


@router.post("/billing/webhooks/{provider}")
async def billing_webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    provider = provider.strip().lower()
    if not provider or len(provider) > 40 or not provider.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=422, detail="Invalid billing provider")
    if not settings.billing_webhook_secret:
        raise HTTPException(status_code=503, detail="Billing webhook secret is not configured")

    raw_body = await request.body()
    signature = request.headers.get("x-billing-signature")
    if not verify_webhook_signature(raw_body, signature, settings.billing_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid billing webhook signature")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Webhook body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Webhook body must be a JSON object")

    event_id = str(payload.get("event_id") or "").strip()
    event_type = str(payload.get("event_type") or "").strip()
    if not event_id or len(event_id) > 180:
        raise HTTPException(status_code=422, detail="event_id is required and must be at most 180 characters")
    if not event_type or len(event_type) > 120:
        raise HTTPException(status_code=422, detail="event_type is required and must be at most 120 characters")

    try:
        event, duplicate = process_payment_event(
            db,
            provider=provider,
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            raw_body=raw_body,
            signature_valid=True,
            grace_days=settings.billing_grace_days,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "accepted": True,
        "duplicate": duplicate,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "processed": event.processed,
    }
