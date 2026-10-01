from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingInvoice, BillingPlan, InvoiceStatus, SubscriptionStatus, TenantSubscription
from app.models.commercial_ops_v2 import BillingContract
from app.services.billing import capture_usage


def get_or_create_contract(db: Session, tenant_id: UUID) -> BillingContract:
    row = db.scalar(select(BillingContract).where(BillingContract.tenant_id == tenant_id))
    if row is None:
        row = BillingContract(tenant_id=tenant_id, billing_interval="annual", auto_renew=True, invoice_lead_days=14, grace_days=7)
        db.add(row)
        db.flush()
    return row


def _period_delta(interval: str) -> timedelta:
    return timedelta(days=365 if interval == "annual" else 30)


def _base_price(plan: BillingPlan, interval: str) -> int:
    if interval == "annual":
        return int(plan.annual_price_minor if plan.annual_price_minor is not None else plan.monthly_price_minor * 12)
    return int(plan.monthly_price_minor)


def generate_contract_invoice(db: Session, subscription: TenantSubscription, contract: BillingContract, now: datetime | None = None) -> BillingInvoice:
    now = now or datetime.now(timezone.utc)
    existing = db.scalar(
        select(BillingInvoice).where(
            BillingInvoice.subscription_id == subscription.id,
            BillingInvoice.period_start == subscription.current_period_start,
            BillingInvoice.period_end == subscription.current_period_end,
            BillingInvoice.status != InvoiceStatus.void,
        )
    )
    if existing is not None:
        return existing

    plan = db.get(BillingPlan, subscription.plan_id)
    if plan is None:
        raise ValueError("Subscription billing plan is unavailable")

    base = _base_price(plan, contract.billing_interval)
    setup = 0 if contract.setup_fee_applied else int(plan.setup_fee_minor or 0)
    subtotal = base + setup
    discount = min(subtotal, (subtotal * max(0, min(100, contract.discount_percent))) // 100)
    after_discount = max(0, subtotal - discount)
    credit_used = min(after_discount, max(0, int(contract.credit_balance_minor)))
    total = max(0, after_discount - credit_used)

    snapshot = capture_usage(db, subscription.tenant_id, subscription.current_period_start, subscription.current_period_end)
    invoice = BillingInvoice(
        tenant_id=subscription.tenant_id,
        subscription_id=subscription.id,
        usage_snapshot_id=snapshot.id,
        invoice_number=f"ITH-{now:%Y%m%d}-{uuid4().hex[:10].upper()}",
        currency=plan.currency,
        subtotal_minor=subtotal,
        total_minor=total,
        status=InvoiceStatus.open if total > 0 else InvoiceStatus.paid,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        due_at=subscription.current_period_end + timedelta(days=contract.grace_days),
        finalized_at=now,
        paid_at=now if total == 0 else None,
    )
    db.add(invoice)
    contract.setup_fee_applied = True
    if credit_used:
        contract.credit_balance_minor -= credit_used
    contract.next_invoice_at = subscription.current_period_end - timedelta(days=contract.invoice_lead_days)
    db.flush()
    return invoice


def run_billing_cycle(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    counters = {"scanned": 0, "invoices_created": 0, "renewed": 0, "past_due": 0, "canceled": 0}
    subscriptions = db.scalars(select(TenantSubscription).order_by(TenantSubscription.current_period_end.asc())).all()

    for subscription in subscriptions:
        counters["scanned"] += 1
        contract = get_or_create_contract(db, subscription.tenant_id)
        if contract.billing_interval not in {"monthly", "annual"}:
            contract.billing_interval = "annual"

        invoice = db.scalar(
            select(BillingInvoice).where(
                BillingInvoice.subscription_id == subscription.id,
                BillingInvoice.period_start == subscription.current_period_start,
                BillingInvoice.period_end == subscription.current_period_end,
                BillingInvoice.status != InvoiceStatus.void,
            )
        )

        lead_at = subscription.current_period_end - timedelta(days=max(0, contract.invoice_lead_days))
        if contract.auto_renew and invoice is None and now >= lead_at and subscription.status in {SubscriptionStatus.trialing, SubscriptionStatus.active, SubscriptionStatus.past_due}:
            invoice = generate_contract_invoice(db, subscription, contract, now=now)
            counters["invoices_created"] += 1

        if now < subscription.current_period_end:
            continue

        if subscription.cancel_at_period_end or not contract.auto_renew:
            subscription.status = SubscriptionStatus.canceled
            counters["canceled"] += 1
            continue

        if invoice is not None and invoice.status == InvoiceStatus.paid:
            previous_end = subscription.current_period_end
            subscription.current_period_start = previous_end
            subscription.current_period_end = previous_end + _period_delta(contract.billing_interval)
            subscription.status = SubscriptionStatus.active
            subscription.past_due_since = None
            subscription.grace_ends_at = None
            contract.next_invoice_at = subscription.current_period_end - timedelta(days=max(0, contract.invoice_lead_days))
            counters["renewed"] += 1
            continue

        if subscription.status != SubscriptionStatus.past_due:
            subscription.status = SubscriptionStatus.past_due
            subscription.past_due_since = now
            subscription.grace_ends_at = now + timedelta(days=max(0, contract.grace_days))
            counters["past_due"] += 1

    db.commit()
    return counters
