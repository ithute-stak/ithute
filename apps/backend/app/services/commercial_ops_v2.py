from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BillingAddon,
    BillingInvoice,
    BillingPlan,
    InvoiceStatus,
    SubscriptionStatus,
    TenantAddon,
    TenantSubscription,
)
from app.models.commercial_ops_v2 import BillingContract
from app.services.billing import capture_usage, tenant_usage
from app.services.catalog_entitlements import rebuild_effective_plan


CAPACITY_FIELDS = (
    "included_mailboxes",
    "included_domains",
    "included_storage_mb",
    "max_api_keys",
    "included_hosted_projects",
    "hosting_storage_mb",
    "hosting_memory_mb_per_project",
    "hosting_cpu_millicores_per_project",
    "hosting_pids_per_project",
    "hosting_database_limit",
    "hosting_database_storage_mb",
    "hosting_source_storage_mb",
)


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


def _base_plan(db: Session, subscription: TenantSubscription) -> BillingPlan:
    plan_id = subscription.base_plan_id or subscription.plan_id
    plan = db.get(BillingPlan, plan_id)
    if plan is None:
        raise ValueError("Subscription base plan is unavailable")
    if subscription.base_plan_id is None:
        subscription.base_plan_id = plan.id
    return plan


def _is_capacity_upgrade(current: BillingPlan, target: BillingPlan) -> bool:
    return all(int(getattr(target, field)) >= int(getattr(current, field)) for field in CAPACITY_FIELDS)


def target_plan_fits_current_usage(db: Session, tenant_id: UUID, target: BillingPlan) -> tuple[bool, list[str]]:
    usage = tenant_usage(db, tenant_id)
    failures: list[str] = []
    checks = {
        "mailboxes": (usage["mailboxes"], target.included_mailboxes),
        "domains": (usage["domains"], target.included_domains),
        "mail storage": (usage["allocated_storage_bytes"], target.included_storage_mb * 1024 * 1024),
        "API keys": (usage["api_keys"], target.max_api_keys),
        "hosted projects": (usage["hosted_projects"], target.included_hosted_projects),
        "application storage": (usage["hosting_storage_bytes"], target.hosting_storage_mb * 1024 * 1024),
        "databases": (usage["hosting_database_count"], target.hosting_database_limit),
        "database storage": (usage["hosting_database_storage_bytes"], target.hosting_database_storage_mb * 1024 * 1024),
        "source storage": (usage["hosting_source_storage_bytes"], target.hosting_source_storage_mb * 1024 * 1024),
    }
    for label, (used, limit) in checks.items():
        if int(used) > int(limit):
            failures.append(f"{label}: {used} used exceeds target limit {limit}")
    return not failures, failures


def request_plan_change(db: Session, subscription: TenantSubscription, target: BillingPlan, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if target.lifecycle_state != "sellable" or not target.is_active or not target.customer_visible:
        raise ValueError("Target package is not available for new plan changes")

    current = _base_plan(db, subscription)
    if current.id == target.id:
        subscription.pending_plan_id = None
        subscription.pending_plan_effective_at = None
        return {"mode": "unchanged", "effective_at": None}

    fits, failures = target_plan_fits_current_usage(db, subscription.tenant_id, target)
    if not fits:
        raise ValueError("Target package is below current usage: " + "; ".join(failures))

    if _is_capacity_upgrade(current, target):
        subscription.base_plan_id = target.id
        subscription.pending_plan_id = None
        subscription.pending_plan_effective_at = None
        rebuild_effective_plan(db, subscription.tenant_id)
        return {"mode": "immediate", "effective_at": now.isoformat()}

    subscription.pending_plan_id = target.id
    subscription.pending_plan_effective_at = subscription.current_period_end
    return {"mode": "period_end", "effective_at": subscription.current_period_end.isoformat()}


def _addon_setup_fees(db: Session, tenant_id: UUID) -> tuple[int, list[TenantAddon]]:
    rows = db.execute(
        select(TenantAddon, BillingAddon)
        .join(BillingAddon, BillingAddon.id == TenantAddon.addon_id)
        .where(
            TenantAddon.tenant_id == tenant_id,
            TenantAddon.status == "active",
            TenantAddon.setup_fee_applied.is_(False),
            BillingAddon.is_active.is_(True),
        )
    ).all()
    total = 0
    assignments: list[TenantAddon] = []
    for assignment, addon in rows:
        total += int(addon.setup_fee_minor or 0) * int(assignment.quantity)
        assignments.append(assignment)
    return total, assignments


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
    plan_setup = 0 if contract.setup_fee_applied else int(plan.setup_fee_minor or 0)
    addon_setup, addon_assignments = _addon_setup_fees(db, subscription.tenant_id)
    subtotal = base + plan_setup + addon_setup
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
    for assignment in addon_assignments:
        assignment.setup_fee_applied = True
    if credit_used:
        contract.credit_balance_minor -= credit_used
    contract.next_invoice_at = subscription.current_period_end - timedelta(days=contract.invoice_lead_days)
    db.flush()
    return invoice


def _apply_period_end_changes(db: Session, subscription: TenantSubscription, now: datetime) -> dict:
    result = {"plan_changed": False, "addons_canceled": 0}

    addons = db.scalars(
        select(TenantAddon).where(
            TenantAddon.tenant_id == subscription.tenant_id,
            TenantAddon.status == "active",
            TenantAddon.cancel_at_period_end.is_(True),
        )
    ).all()
    for assignment in addons:
        assignment.status = "canceled"
        assignment.canceled_at = now
        assignment.cancel_at_period_end = False
        assignment.current_period_end = now
        result["addons_canceled"] += 1

    if subscription.pending_plan_id is not None and (
        subscription.pending_plan_effective_at is None or subscription.pending_plan_effective_at <= now
    ):
        target = db.get(BillingPlan, subscription.pending_plan_id)
        if target is not None and target.lifecycle_state == "sellable" and target.is_active:
            fits, _failures = target_plan_fits_current_usage(db, subscription.tenant_id, target)
            if fits:
                subscription.base_plan_id = target.id
                subscription.pending_plan_id = None
                subscription.pending_plan_effective_at = None
                result["plan_changed"] = True

    if result["plan_changed"] or result["addons_canceled"]:
        rebuild_effective_plan(db, subscription.tenant_id)
    return result


def run_billing_cycle(db: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    counters = {
        "scanned": 0,
        "invoices_created": 0,
        "renewed": 0,
        "past_due": 0,
        "canceled": 0,
        "plan_changes_applied": 0,
        "addons_canceled": 0,
    }
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
            changes = _apply_period_end_changes(db, subscription, now)
            counters["plan_changes_applied"] += int(changes["plan_changed"])
            counters["addons_canceled"] += int(changes["addons_canceled"])
            previous_end = subscription.current_period_end
            subscription.current_period_start = previous_end
            subscription.current_period_end = previous_end + _period_delta(contract.billing_interval)
            subscription.status = SubscriptionStatus.active
            subscription.past_due_since = None
            subscription.grace_ends_at = None
            active_addons = db.scalars(select(TenantAddon).where(TenantAddon.tenant_id == subscription.tenant_id, TenantAddon.status == "active")).all()
            for assignment in active_addons:
                assignment.current_period_start = subscription.current_period_start
                assignment.current_period_end = subscription.current_period_end
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
