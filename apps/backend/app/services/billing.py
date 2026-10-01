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
    HostingProject,
    InvoiceStatus,
    Mailbox,
    MailboxStatus,
    SubscriptionStatus,
    TenantSubscription,
    UsageSnapshot,
)
from app.services.hosting_metering import hosting_resource_usage

DEFAULT_PLANS = (
    {
        "code": "starter",
        "name": "Ithute Start",
        "currency": "LSL",
        "monthly_price_minor": 18_500,
        "included_mailboxes": 10,
        "included_domains": 2,
        "included_storage_mb": 50_000,
        "max_api_keys": 3,
        "included_hosted_projects": 1,
        "hosting_storage_mb": 1024,
        "hosting_memory_mb_per_project": 512,
        "hosting_cpu_millicores_per_project": 500,
        "hosting_pids_per_project": 128,
        "hosting_database_limit": 2,
        "hosting_database_storage_mb": 1024,
        "hosting_source_storage_mb": 1024,
        "product_category": "Website & Hosting",
        "description": "Professional starter website, hosting, business email and essential brand setup.",
        "website_pages": 1,
        "includes_website_design": True,
        "includes_logo_design": True,
        "includes_brand_guide": False,
        "includes_company_profile": False,
        "includes_letterhead": False,
        "includes_page_headers_footers": True,
        "includes_business_templates": False,
        "included_revisions": 1,
        "content_updates_per_month": 0,
        "support_level": "standard",
        "minimum_term_months": 12,
        "price_from": False,
    },
    {
        "code": "grow",
        "name": "Ithute Grow",
        "currency": "LSL",
        "monthly_price_minor": 29_500,
        "included_mailboxes": 15,
        "included_domains": 3,
        "included_storage_mb": 75 * 1024,
        "max_api_keys": 5,
        "included_hosted_projects": 1,
        "hosting_storage_mb": 2 * 1024,
        "hosting_memory_mb_per_project": 768,
        "hosting_cpu_millicores_per_project": 750,
        "hosting_pids_per_project": 192,
        "hosting_database_limit": 2,
        "hosting_database_storage_mb": 2 * 1024,
        "hosting_source_storage_mb": 2 * 1024,
        "product_category": "Website & Hosting",
        "description": "Growing-business website and brand package with professional documents and light monthly content support.",
        "website_pages": 5,
        "includes_website_design": True,
        "includes_logo_design": True,
        "includes_brand_guide": True,
        "includes_company_profile": False,
        "includes_letterhead": True,
        "includes_page_headers_footers": True,
        "includes_business_templates": False,
        "included_revisions": 2,
        "content_updates_per_month": 1,
        "support_level": "standard",
        "minimum_term_months": 12,
        "price_from": False,
    },
    {
        "code": "business",
        "name": "Ithute Business",
        "currency": "LSL",
        "monthly_price_minor": 49_500,
        "included_mailboxes": 50,
        "included_domains": 10,
        "included_storage_mb": 250_000,
        "max_api_keys": 10,
        "included_hosted_projects": 3,
        "hosting_storage_mb": 5120,
        "hosting_memory_mb_per_project": 1024,
        "hosting_cpu_millicores_per_project": 1000,
        "hosting_pids_per_project": 256,
        "hosting_database_limit": 6,
        "hosting_database_storage_mb": 5120,
        "hosting_source_storage_mb": 5120,
        "product_category": "Website & Hosting",
        "description": "Complete SME website, hosting and corporate identity package with business document templates.",
        "website_pages": 8,
        "includes_website_design": True,
        "includes_logo_design": True,
        "includes_brand_guide": True,
        "includes_company_profile": True,
        "includes_letterhead": True,
        "includes_page_headers_footers": True,
        "includes_business_templates": True,
        "included_revisions": 3,
        "content_updates_per_month": 2,
        "support_level": "priority",
        "minimum_term_months": 12,
        "price_from": False,
    },
    {
        "code": "professional",
        "name": "Ithute Professional",
        "currency": "LSL",
        "monthly_price_minor": 79_500,
        "included_mailboxes": 75,
        "included_domains": 15,
        "included_storage_mb": 375 * 1024,
        "max_api_keys": 15,
        "included_hosted_projects": 5,
        "hosting_storage_mb": 8 * 1024,
        "hosting_memory_mb_per_project": 1536,
        "hosting_cpu_millicores_per_project": 1500,
        "hosting_pids_per_project": 384,
        "hosting_database_limit": 10,
        "hosting_database_storage_mb": 8 * 1024,
        "hosting_source_storage_mb": 8 * 1024,
        "product_category": "Website & Hosting",
        "description": "Advanced website and managed-system package with full brand identity, company profile and priority support.",
        "website_pages": 12,
        "includes_website_design": True,
        "includes_logo_design": True,
        "includes_brand_guide": True,
        "includes_company_profile": True,
        "includes_letterhead": True,
        "includes_page_headers_footers": True,
        "includes_business_templates": True,
        "included_revisions": 5,
        "content_updates_per_month": 4,
        "support_level": "priority",
        "minimum_term_months": 12,
        "price_from": False,
    },
    {
        "code": "enterprise",
        "name": "Ithute Enterprise",
        "currency": "LSL",
        "monthly_price_minor": 150_000,
        "included_mailboxes": 200,
        "included_domains": 50,
        "included_storage_mb": 1_000_000,
        "max_api_keys": 50,
        "included_hosted_projects": 10,
        "hosting_storage_mb": 10240,
        "hosting_memory_mb_per_project": 2048,
        "hosting_cpu_millicores_per_project": 2000,
        "hosting_pids_per_project": 512,
        "hosting_database_limit": 20,
        "hosting_database_storage_mb": 10240,
        "hosting_source_storage_mb": 10240,
        "product_category": "Website & Hosting",
        "description": "Custom digital presence, managed systems, hosting and full corporate branding for larger organizations.",
        "website_pages": 20,
        "includes_website_design": True,
        "includes_logo_design": True,
        "includes_brand_guide": True,
        "includes_company_profile": True,
        "includes_letterhead": True,
        "includes_page_headers_footers": True,
        "includes_business_templates": True,
        "included_revisions": 8,
        "content_updates_per_month": 8,
        "support_level": "dedicated",
        "minimum_term_months": 12,
        "price_from": True,
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
    mailboxes = db.scalar(select(func.count(Mailbox.id)).where(Mailbox.tenant_id == tenant_id, Mailbox.status != MailboxStatus.archived)) or 0
    domains = db.scalar(select(func.count(Domain.id)).where(Domain.tenant_id == tenant_id, Domain.status != DomainStatus.archived)) or 0
    allocated_storage_bytes = db.scalar(select(func.coalesce(func.sum(Mailbox.quota_bytes), 0)).where(Mailbox.tenant_id == tenant_id, Mailbox.status != MailboxStatus.archived)) or 0
    api_keys = db.scalar(select(func.count(ApiKey.id)).where(ApiKey.tenant_id == tenant_id, ApiKey.revoked_at.is_(None))) or 0
    hosted_projects = db.scalar(select(func.count(HostingProject.id)).where(HostingProject.tenant_id == tenant_id)) or 0
    hosting_storage_mb = db.scalar(select(func.coalesce(func.sum(HostingProject.storage_mb), 0)).where(HostingProject.tenant_id == tenant_id)) or 0
    shared_usage = hosting_resource_usage(db, tenant_id)
    return {
        "mailboxes": int(mailboxes),
        "domains": int(domains),
        "allocated_storage_bytes": int(allocated_storage_bytes),
        "api_keys": int(api_keys),
        "hosted_projects": int(hosted_projects),
        "hosting_storage_bytes": int(hosting_storage_mb) * 1024 * 1024,
        "hosting_database_count": shared_usage["database_count"],
        "hosting_database_storage_bytes": shared_usage["database_storage_bytes"],
        "hosting_source_storage_bytes": shared_usage["source_storage_bytes"],
    }


def capture_usage(db: Session, tenant_id: UUID, period_start: datetime | None = None, period_end: datetime | None = None) -> UsageSnapshot:
    usage = tenant_usage(db, tenant_id)
    snapshot = UsageSnapshot(
        tenant_id=tenant_id,
        mailboxes=usage["mailboxes"],
        domains=usage["domains"],
        storage_bytes=usage["allocated_storage_bytes"],
        hosting_database_count=usage["hosting_database_count"],
        hosting_database_storage_bytes=usage["hosting_database_storage_bytes"],
        hosting_source_storage_bytes=usage["hosting_source_storage_bytes"],
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
        subscription = TenantSubscription(tenant_id=tenant_id, plan_id=plan.id, status=status, current_period_start=now, current_period_end=now + timedelta(days=period_days), provider="manual")
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
        "hosted_projects": plan.included_hosted_projects,
        "hosting_storage_bytes": plan.hosting_storage_mb * 1024 * 1024,
        "hosting_memory_mb_per_project": plan.hosting_memory_mb_per_project,
        "hosting_cpu_millicores_per_project": plan.hosting_cpu_millicores_per_project,
        "hosting_pids_per_project": plan.hosting_pids_per_project,
        "hosting_database_count": plan.hosting_database_limit,
        "hosting_database_storage_bytes": plan.hosting_database_storage_mb * 1024 * 1024,
        "hosting_source_storage_bytes": plan.hosting_source_storage_mb * 1024 * 1024,
    }


def entitlement_decision(db: Session, tenant_id: UUID, resource: str, requested_storage_bytes: int = 0, now: datetime | None = None) -> dict:
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
        "hosting_project": limits["hosted_projects"] > 0 and usage["hosted_projects"] + 1 <= limits["hosted_projects"] and usage["hosting_storage_bytes"] + requested_storage_bytes <= limits["hosting_storage_bytes"],
        "hosting_storage": usage["hosting_storage_bytes"] + requested_storage_bytes <= limits["hosting_storage_bytes"],
        "hosting_database": usage["hosting_database_count"] + 1 <= limits["hosting_database_count"] and usage["hosting_database_storage_bytes"] + requested_storage_bytes <= limits["hosting_database_storage_bytes"],
        "hosting_database_storage": usage["hosting_database_storage_bytes"] + requested_storage_bytes <= limits["hosting_database_storage_bytes"],
        "hosting_source_storage": usage["hosting_source_storage_bytes"] + requested_storage_bytes <= limits["hosting_source_storage_bytes"],
    }
    if resource not in checks:
        raise ValueError(f"Unknown entitlement resource: {resource}")
    return {"allowed": checks[resource], "reason": "within plan" if checks[resource] else f"{resource} entitlement limit reached", "usage": usage, "limits": limits, "subscription_status": subscription.status.value, "grace_ends_at": subscription.grace_ends_at.isoformat() if subscription.grace_ends_at else None}


def require_entitlement(db: Session, tenant_id: UUID, resource: str, requested_storage_bytes: int = 0) -> None:
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
    existing = db.scalar(select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id, BillingInvoice.period_start == subscription.current_period_start, BillingInvoice.period_end == subscription.current_period_end, BillingInvoice.status != InvoiceStatus.void))
    if existing is not None:
        return existing
    snapshot = capture_usage(db, tenant_id, subscription.current_period_start, subscription.current_period_end)
    now = datetime.now(timezone.utc)
    invoice = BillingInvoice(tenant_id=tenant_id, subscription_id=subscription.id, usage_snapshot_id=snapshot.id, invoice_number=f"MDNS-{now:%Y%m%d}-{uuid4().hex[:10].upper()}", currency=plan.currency, subtotal_minor=plan.monthly_price_minor, total_minor=plan.monthly_price_minor, status=InvoiceStatus.open, period_start=subscription.current_period_start, period_end=subscription.current_period_end, due_at=now + timedelta(days=due_days), finalized_at=now)
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


def process_payment_event(db: Session, provider: str, event_id: str, event_type: str, payload: dict, raw_body: bytes, signature_valid: bool, grace_days: int = 7) -> tuple[BillingPaymentEvent, bool]:
    provider = provider.strip().lower()
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    existing = db.scalar(select(BillingPaymentEvent).where(BillingPaymentEvent.provider == provider, BillingPaymentEvent.event_id == event_id))
    if existing is not None:
        if existing.payload_hash != payload_hash or existing.event_type != event_type:
            raise ValueError("Webhook event_id was reused with different content")
        return existing, True
    tenant_id = UUID(str(payload["tenant_id"])) if payload.get("tenant_id") else None
    invoice_id = UUID(str(payload["invoice_id"])) if payload.get("invoice_id") else None
    event = BillingPaymentEvent(provider=provider, event_id=event_id, event_type=event_type, tenant_id=tenant_id, invoice_id=invoice_id, payload_hash=payload_hash, signature_valid=signature_valid, processed=False)
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
    return {"id": str(invoice.id), "tenant_id": str(invoice.tenant_id), "subscription_id": str(invoice.subscription_id) if invoice.subscription_id else None, "usage_snapshot_id": str(invoice.usage_snapshot_id) if invoice.usage_snapshot_id else None, "invoice_number": invoice.invoice_number, "currency": invoice.currency, "subtotal_minor": invoice.subtotal_minor, "total_minor": invoice.total_minor, "status": invoice.status.value, "period_start": invoice.period_start.isoformat() if invoice.period_start else None, "period_end": invoice.period_end.isoformat() if invoice.period_end else None, "due_at": invoice.due_at.isoformat() if invoice.due_at else None, "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None, "finalized_at": invoice.finalized_at.isoformat() if invoice.finalized_at else None, "provider_invoice_id": invoice.provider_invoice_id, "created_at": invoice.created_at.isoformat() if invoice.created_at else None}


def billing_summary(db: Session, tenant_id: UUID) -> dict:
    usage = tenant_usage(db, tenant_id)
    subscription = get_subscription(db, tenant_id)
    if subscription is None:
        return {"subscription": None, "usage": usage, "entitlements": None, "within_plan": False}
    entitlement_plan = db.get(BillingPlan, subscription.plan_id)
    if entitlement_plan is None:
        return {"subscription": {"id": str(subscription.id), "status": subscription.status.value}, "usage": usage, "entitlements": None, "within_plan": False}
    base_plan = db.get(BillingPlan, subscription.base_plan_id or subscription.plan_id) or entitlement_plan
    pending_plan = db.get(BillingPlan, subscription.pending_plan_id) if subscription.pending_plan_id else None
    limits = _limits(entitlement_plan)
    within = (
        usage["mailboxes"] <= limits["mailboxes"]
        and usage["domains"] <= limits["domains"]
        and usage["allocated_storage_bytes"] <= limits["storage_bytes"]
        and usage["api_keys"] <= limits["api_keys"]
        and usage["hosted_projects"] <= limits["hosted_projects"]
        and usage["hosting_storage_bytes"] <= limits["hosting_storage_bytes"]
        and usage["hosting_database_count"] <= limits["hosting_database_count"]
        and usage["hosting_database_storage_bytes"] <= limits["hosting_database_storage_bytes"]
        and usage["hosting_source_storage_bytes"] <= limits["hosting_source_storage_bytes"]
    )
    return {
        "subscription": {
            "id": str(subscription.id),
            "status": subscription.status.value,
            "plan_code": base_plan.code,
            "plan_name": base_plan.name,
            "base_plan_code": base_plan.code,
            "base_plan_name": base_plan.name,
            "entitlement_plan_code": entitlement_plan.code,
            "entitlement_plan_name": entitlement_plan.name,
            "pending_plan_code": pending_plan.code if pending_plan else None,
            "pending_plan_name": pending_plan.name if pending_plan else None,
            "pending_plan_effective_at": subscription.pending_plan_effective_at.isoformat() if subscription.pending_plan_effective_at else None,
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
