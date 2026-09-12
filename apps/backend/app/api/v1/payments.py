import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, BillingInvoice, BillingPaymentEvent, CustomerProfile, InvoiceStatus, SubscriptionStatus, TenantSubscription, User
from app.services.commercial_providers import (
    ProviderConfigurationError,
    ProviderRequestError,
    dpo_configured,
    dpo_create_token,
    dpo_verify_token,
)

router = APIRouter(tags=["payments"])


@router.get("/public/payment-provider")
def payment_provider_status():
    return {"provider": "dpo", "configured": dpo_configured(), "hosted_checkout": True}


@router.post("/tenants/{tenant_id}/billing/invoices/{invoice_id}/dpo-checkout")
def create_dpo_checkout(
    tenant_id: UUID,
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    invoice = db.get(BillingInvoice, invoice_id)
    if invoice is None or invoice.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.paid:
        raise HTTPException(status_code=409, detail="Invoice is already paid")
    if invoice.status not in {InvoiceStatus.open, InvoiceStatus.draft}:
        raise HTTPException(status_code=409, detail="Invoice cannot be paid in its current state")
    profile = db.scalar(select(CustomerProfile).where(CustomerProfile.tenant_id == tenant_id))
    try:
        checkout = dpo_create_token(
            amount_minor=invoice.total_minor,
            currency=invoice.currency,
            reference=invoice.invoice_number,
            description=f"Mailbox DNS invoice {invoice.invoice_number}",
            customer_email=profile.billing_email if profile else None,
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    invoice.provider_invoice_id = checkout["token"]
    if invoice.status == InvoiceStatus.draft:
        invoice.status = InvoiceStatus.open
        invoice.finalized_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        tenant_id=tenant_id,
        actor_user_id=current.id,
        action="billing.dpo_checkout.create",
        resource_type="billing_invoice",
        resource_id=str(invoice.id),
    ))
    db.commit()
    return checkout


def _complete_dpo_payment(db: Session, token: str) -> dict:
    invoice = db.scalar(select(BillingInvoice).where(BillingInvoice.provider_invoice_id == token))
    if invoice is None:
        raise HTTPException(status_code=404, detail="DPO transaction is not linked to an invoice")
    try:
        verification = dpo_verify_token(token)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result = verification.get("Result")
    event_id = f"{token}:{result}:{verification.get('TransactionApproval', '')}"
    payload_hash = hashlib.sha256(repr(sorted(verification.items())).encode("utf-8")).hexdigest()
    existing = db.scalar(select(BillingPaymentEvent).where(BillingPaymentEvent.provider == "dpo", BillingPaymentEvent.event_id == event_id))
    if existing is None:
        event = BillingPaymentEvent(
            provider="dpo",
            event_id=event_id,
            event_type="verifyToken",
            payload_hash=payload_hash,
            signature_valid=True,
            processed=True,
            tenant_id=invoice.tenant_id,
            invoice_id=invoice.id,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(event)
    if result == "000":
        invoice.status = InvoiceStatus.paid
        invoice.paid_at = datetime.now(timezone.utc)
        if invoice.subscription_id:
            subscription = db.get(TenantSubscription, invoice.subscription_id)
            if subscription:
                subscription.status = SubscriptionStatus.active
                subscription.past_due_since = None
                subscription.grace_ends_at = None
                subscription.provider = "dpo"
        db.add(AuditLog(
            tenant_id=invoice.tenant_id,
            action="billing.dpo_payment.verified",
            resource_type="billing_invoice",
            resource_id=str(invoice.id),
        ))
    db.commit()
    return {
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "paid": invoice.status == InvoiceStatus.paid,
        "provider_result": result,
        "provider_explanation": verification.get("ResultExplanation"),
    }


@router.get("/payments/dpo/callback")
def dpo_callback_get(TransactionToken: str | None = None, TransToken: str | None = None, db: Session = Depends(get_db)):
    token = TransactionToken or TransToken
    if not token:
        raise HTTPException(status_code=422, detail="Missing DPO transaction token")
    return _complete_dpo_payment(db, token)


@router.post("/payments/dpo/callback")
async def dpo_callback_post(request: Request, db: Session = Depends(get_db)):
    token = request.query_params.get("TransactionToken") or request.query_params.get("TransToken")
    if not token:
        try:
            form = await request.form()
            token = form.get("TransactionToken") or form.get("TransToken")
        except Exception:
            token = None
    if not token:
        raise HTTPException(status_code=422, detail="Missing DPO transaction token")
    return _complete_dpo_payment(db, str(token))
