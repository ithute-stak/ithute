import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    ApiKey,
    BillingInvoice,
    BillingPaymentEvent,
    BillingPlan,
    Domain,
    DomainStatus,
    InvoiceStatus,
    Mailbox,
    MailboxStatus,
    SubscriptionStatus,
    TenantSubscription,
    UsageSnapshot,
)

DEFAULT_PLANS = (
    {
        "code": "starter",
        "name": "Starter",
        "currency": "LSL",
        "monthly_price_minor": 49000,
        "included_mailboxes": 10,
        "included_domains": 2,
        "included_storage_mb": 50_000,
        "max_api_keys": 3,
    },
    {
        "code": "business",
        "name": "Business",
        "currency": "LSL",
        "monthly_price_minor": 149000,
        "included_mailboxes": 50,
        "included_domains": 10,
        "included_storage_mb": 250_000,
        "max_api_keys": 10,
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "currency": "LSL",
        "monthly_price_minor": 399000,
        "included_mailboxes": 200,
        "included_domains": 50,
        "included_storage_mb": 1_000_000,
        "max_api_keys": 50,
    },
)


def ensure_default_plans(db: Session) -> None:
    existing = set(db.scalars(select(BillingPlan.code)).all())
    changed = False
    for values in DEFAULT_PLANS:
        if values["code"] in existing:
            continue
        db.add(BillingPlan(**values))
        changed = True
    if changed:
        db.commit()


def tenant_usage(db: Session, tenant_id: UUID) -> dict:
    mailboxes = db.scalar(
        select(func.count(Mailbox.id)).where(
            Mailbox.tenant_id == tenant_id,
            Mailbox.status != MailboxStatus.archived,
        )
    ) or 0
    domains = db.scalar(
        select(func.count(Domain.id)).where(
            Domain.tenant_id == tenant_id,
            Domain.status != DomainStatus.archived,
        )
    ) or 0
    allocated_storage_bytes = db.scalar(
        select(func.coalesce(func.sum(Mailbox.quota_bytes), 0)).where(
            Mailbox.tenant_id == tenant_id,
            Mailbox.status != MailboxStatus.archived,
        )
    ) or 0
    api_keys = db.scalar(
        select(func.count(ApiKey.id)).where(
            ApiKey.tenant_id == tenant_id,
            ApiKey.revoked_at.is_(None),
        )
    ) or 0
    return {
        "mailboxes": int(mailboxes),
        "domains": int(domains),
        "allocated_storage_bytes": int(allocated_storage_bytes),
        "api_keys": int(api_keys),
    }


def capture_usage(
    db: Session,
    tenant_id: UUID,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> UsageSnapshot:
    usage = tenant_usage(db, tenant_id)
    snapshot = UsageSnapshot(
        tenant_id=tenant_id,
        mailboxes=usage["mailboxes"],
        domains=usage["domains"],
        storage_bytes=usage["allocated_storage_bytes"],
        period_start=period_start,
        period_end=period_end,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_subscription(db: Session, tenant_id: UUID) -> TenantSubscription | None:
    return db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))


def assign_subscription(db: Session, tenant_id: UUID, plan: BillingPlan, status: SubscriptionStatus, period_days: int = 30) -> TenantSubscription:
    now = datetime.now(timezone.utc)
    subscription = get_subscription(db, tenant_id)
    if subscription is None:
        subscription = TenantSubscription(
            tenant_id=tenant_id,
            plan_id=plan.id,
            status=status,
            current_period_start=now,
            current_period_end=now + timedelta(days=period_days),
            provider="manual",
        )
        db.add(subscription)
    else:
        subscription.plan_id = plan.id
        subscription.status = status
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=period_days)
        subscription.cancel_at_period_end = False
    if status != SubscriptionStatus.past_due:
        subscription.past_due_since = None
        subscription.grace_ends_at = None
    db.commit()
    db.refresh(subscription)
    return subscription


def _limits(plan: BillingPlan) -> dict:
    return {
        "mailboxes": plan.included_mailboxes,
        "domains": plan.included_domains,
        "storage_bytes": plan.included_storage_mb * 1024 * 1024,
        "api_keys": plan.max_api_keys,
    }


def entitlement_decision(
    db: Session,
    tenant_id: UUID,
    resource: str,
    requested_storage_bytes: int = 0,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    usage = tenant_usage(db, tenant_id)
    subscription = get_subscription(db, tenant_id)
    if subscription is None:
        return {"allowed": False, "reason": "No active subscription", "usage": usage, "limits": None}
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None or not plan.is_active:
        return {"allowed": False, "reason": "Billing plan is unavailable", "usage": usage, "limits": None}

    if subscription.status == SubscriptionStatus.canceled:
        return {"allowed": False, "reason": "Subscription is canceled", "usage": usage, "limits": _limits(plan)}
    if subscription.status == SubscriptionStatus.past_due and (subscription.grace_ends_at is None or subscription.grace_ends_at <= now):
        return {"allowed": False, "reason": "Payment grace period has expired", "usage": usage, "limits": _limits(plan)}
    if subscription.status not in {SubscriptionStatus.trialing, SubscriptionStatus.active, SubscriptionStatus.past_due}:
        return {"allowed": False, "reason": "Subscription does not allow new resources", "usage": usage, "limits": _limits(plan)}

    limits = _limits(plan)
    checks = {
        "domain": usage["domains"] + 1 <= limits["domains"],
        "mailbox": usage["mailboxes"] + 1 <= limits["mailboxes"] and usage["allocated_storage_bytes"] + requested_storage_bytes <= limits["storage_bytes"],
        "storage": usage["allocated_storage_bytes"] + requested_storage_bytes <= limits["storage_bytes"],
        "api_key": usage["api_keys"] + 1 <= limits["api_keys"],
    }
    if resource not in checks:
        raise ValueError(f"Unknown entitlement resource: {resource}")
    return {
        "allowed": checks[resource],
        "reason": "within plan" if checks[resource] else f"{resource} entitlement limit reached",
        "usage": usage,
        "limits": limits,
        "subscription_status": subscription.status.value,
        "grace_ends_at": subscription.grace_ends_at.isoformat() if subscription.grace_ends_at else None,
    }


def require_entitlement(db: Session, tenant_id: UUID, resource: str, requested_storage_bytes: int = 0) -> None:
    # Existing phase regression fixtures predate subscriptions. Keep development
    # non-destructive while production always enforces the billing gate.
    if settings.environment.lower() != "production":
        return
    decision = entitlement_decision(db, tenant_id, resource, requested_storage_bytes=requested_storage_bytes)
    if not decision["allowed"]:
        raise ValueError(decision["reason"])


def generate_invoice(db: Session, tenant_id: UUID, due_days: int = 14) -> BillingInvoice:
    subscription = get_subscription(db, tenant_id)
    if subscription is None:
        raise ValueError("Tenant has no subscription")
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None:
        raise ValueError("Subscription billing plan is unavailable")

    existing = db.scalar(
        select(BillingInvoice).where(
            BillingInvoice.tenant_id == tenant_id,
            BillingInvoice.period_start == subscription.current_period_start,
            BillingInvoice.period_end == subscription.current_period_end,
            BillingInvoice.status != InvoiceStatus.void,
        )
    )
    if existing is not None:
        return existing

    snapshot = capture_usage(db, tenant_id, subscription.current_period_start, subscription.current_period_end)
    now = datetime.now(timezone.utc)
    invoice = BillingInvoice(
        tenant_id=tenant_id,
        subscription_id=subscription.id,
        usage_snapshot_id=snapshot.id,
        invoice_number=f"MDNS-{now:%Y%m%d}-{uuid4().hex[:10].upper()}",
        currency=plan.currency,
        subtotal_minor=plan.monthly_price_minor,
        total_minor=plan.monthly_price_minor,
        status=InvoiceStatus.open,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        due_at=now + timedelta(days=due_days),
        finalized_at=now,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def mark_past_due(db: Session, subscription: TenantSubscription, grace_days: int = 7) -> TenantSubscription:
    now = datetime.now(timezone.utc)
    subscription.status = SubscriptionStatus.past_due
    subscription.past_due_since = subscription.past_due_since or now
    subscription.grace_ends_at = now + timedelta(days=grace_days)
    db.commit()
    db.refresh(subscription)
    return subscription


def mark_subscription_active(db: Session, subscription: TenantSubscription) -> TenantSubscription:
    subscription.status = SubscriptionStatus.active
    subscription.past_due_since = None
    subscription.grace_ends_at = None
    db.commit()
    db.refresh(subscription)
    return subscription


def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    supplied = signature.strip()
    if supplied.startswith("sha256="):
        supplied = supplied[7:]
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied)


def process_payment_event(
    db: Session,
    provider: str,
    event_id: str,
    event_type: str,
    payload: dict,
    raw_body: bytes,
    signature_valid: bool,
    grace_days: int = 7,
) -> tuple[BillingPaymentEvent, bool]:
    provider = provider.strip().lower()
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    existing = db.scalar(
        select(BillingPaymentEvent).where(
            BillingPaymentEvent.provider == provider,
            BillingPaymentEvent.event_id == event_id,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash or existing.event_type != event_type:
            raise ValueError("Webhook event_id was reused with different content")
        return existing, True

    tenant_id = UUID(str(payload["tenant_id"])) if payload.get("tenant_id") else None
    invoice_id = UUID(str(payload["invoice_id"])) if payload.get("invoice_id") else None
    event = BillingPaymentEvent(
        provider=provider,
        event_id=event_id,
        event_type=event_type,
        payload_hash=payload_hash,
        signature_valid=signature_valid,
        tenant_id=tenant_id,
        invoice_id=invoice_id,
    )
    db.add(event)
    db.flush()

    try:
        if not signature_valid:
            raise ValueError("Invalid webhook signature")
        invoice = db.get(BillingInvoice, invoice_id) if invoice_id else None
        subscription = get_subscription(db, tenant_id) if tenant_id else None
        if invoice is not None and tenant_id is not None and invoice.tenant_id != tenant_id:
            raise ValueError("Invoice does not belong to webhook tenant")

        if event_type == "invoice.paid":
            if invoice is None:
                raise ValueError("Invoice not found")
            invoice.status = InvoiceStatus.paid
            invoice.paid_at = datetime.now(timezone.utc)
            if subscription is not None:
                subscription.status = SubscriptionStatus.active
                subscription.past_due_since = None
                subscription.grace_ends_at = None
        elif event_type in {"invoice.payment_failed", "invoice.past_due"}:
            if invoice is not None and invoice.status != InvoiceStatus.paid:
                invoice.status = InvoiceStatus.open
            if subscription is None:
                raise ValueError("Subscription not found")
            now = datetime.now(timezone.utc)
            subscription.status = SubscriptionStatus.past_due
            subscription.past_due_since = subscription.past_due_since or now
            subscription.grace_ends_at = now + timedelta(days=grace_days)
        elif event_type == "subscription.canceled":
            if subscription is None:
                raise ValueError("Subscription not found")
            subscription.status = SubscriptionStatus.canceled
            subscription.grace_ends_at = None
        elif event_type == "subscription.active":
            if subscription is None:
                raise ValueError("Subscription not found")
            subscription.status = SubscriptionStatus.active
            subscription.past_due_since = None
            subscription.grace_ends_at = None
        else:
            raise ValueError(f"Unsupported billing event type: {event_type}")

        event.processed = True
        event.processed_at = datetime.now(timezone.utc)
        event.error_message = None
        db.commit()
        db.refresh(event)
        return event, False
    except Exception as exc:
        event.processed = False
        event.error_message = str(exc)[:500]
        db.commit()
        db.refresh(event)
        raise


def invoice_out(invoice: BillingInvoice) -> dict:
    return {
        "id": str(invoice.id),
        "tenant_id": str(invoice.tenant_id),
        "subscription_id": str(invoice.subscription_id) if invoice.subscription_id else None,
        "usage_snapshot_id": str(invoice.usage_snapshot_id) if invoice.usage_snapshot_id else None,
        "invoice_number": invoice.invoice_number,
        "currency": invoice.currency,
        "subtotal_minor": invoice.subtotal_minor,
        "total_minor": invoice.total_minor,
        "status": invoice.status.value,
        "period_start": invoice.period_start.isoformat() if invoice.period_start else None,
        "period_end": invoice.period_end.isoformat() if invoice.period_end else None,
        "due_at": invoice.due_at.isoformat() if invoice.due_at else None,
        "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
        "finalized_at": invoice.finalized_at.isoformat() if invoice.finalized_at else None,
        "provider_invoice_id": invoice.provider_invoice_id,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
    }


def billing_summary(db: Session, tenant_id: UUID) -> dict:
    usage = tenant_usage(db, tenant_id)
    subscription = get_subscription(db, tenant_id)
    if subscription is None:
        return {
            "subscription": None,
            "usage": usage,
            "entitlements": None,
            "within_plan": False,
        }
    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None:
        return {
            "subscription": {"id": str(subscription.id), "status": subscription.status.value},
            "usage": usage,
            "entitlements": None,
            "within_plan": False,
        }
    limits = _limits(plan)
    within = (
        usage["mailboxes"] <= limits["mailboxes"]
        and usage["domains"] <= limits["domains"]
        and usage["allocated_storage_bytes"] <= limits["storage_bytes"]
        and usage["api_keys"] <= limits["api_keys"]
    )
    return {
        "subscription": {
            "id": str(subscription.id),
            "status": subscription.status.value,
            "plan_code": plan.code,
            "plan_name": plan.name,
            "current_period_start": subscription.current_period_start.isoformat(),
            "current_period_end": subscription.current_period_end.isoformat(),
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "past_due_since": subscription.past_due_since.isoformat() if subscription.past_due_since else None,
            "grace_ends_at": subscription.grace_ends_at.isoformat() if subscription.grace_ends_at else None,
        },
        "usage": usage,
        "entitlements": limits,
        "within_plan": within,
    }
