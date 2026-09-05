#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml -f docker-compose.phase11-backup.yml -f docker-compose.phase12-monitoring.yml"

printf '\n== Phase 13: Phase 12 regression gate ==\n'
sh scripts/verify-phase12.sh

printf '\n== Phase 13: rebuild billing-aware backend and migrate ==\n'
$COMPOSE build backend
$COMPOSE up -d --force-recreate backend
for i in $(seq 1 30); do
  if $COMPOSE exec -T backend curl -fsS http://localhost:8000/health/ready >/dev/null 2>&1; then break; fi
  sleep 2
done
$COMPOSE exec -T backend curl -fsS http://localhost:8000/health/ready >/dev/null
CURRENT_REV="$($COMPOSE exec -T backend alembic current 2>/dev/null | awk 'NF {print $1; exit}')"
HEAD_REV="$($COMPOSE exec -T backend alembic heads 2>/dev/null | awk 'NF {print $1; exit}')"
[ -n "$CURRENT_REV" ] && [ "$CURRENT_REV" = "$HEAD_REV" ] || { echo "Alembic database is not at head: current=$CURRENT_REV head=$HEAD_REV"; exit 1; }
$COMPOSE exec -T backend alembic history | grep -q '0007_billing_operations'
echo "Phase 13 historical migration present; database current head: $CURRENT_REV"

printf '\n== Phase 13: compile and billing operations acceptance ==\n'
$COMPOSE exec -T backend python -m compileall -q app
$COMPOSE exec -T backend python - <<'PY'
import json
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import inspect, select

from app.db.session import SessionLocal, engine
from app.models import BillingPaymentEvent, BillingPlan, SubscriptionStatus, Tenant
from app.services.billing import (
    assign_subscription,
    billing_summary,
    capture_usage,
    ensure_default_plans,
    entitlement_decision,
    generate_invoice,
    process_payment_event,
    verify_webhook_signature,
)

required_tables = {
    "billing_plans",
    "tenant_subscriptions",
    "usage_snapshots",
    "billing_invoices",
    "billing_payment_events",
}
tables = set(inspect(engine).get_table_names())
assert required_tables <= tables, required_tables - tables

with SessionLocal() as db:
    ensure_default_plans(db)
    ensure_default_plans(db)
    plans = db.scalars(select(BillingPlan).order_by(BillingPlan.monthly_price_minor)).all()
    codes = [plan.code for plan in plans if plan.is_active]
    assert {"starter", "business", "enterprise"} <= set(codes)
    assert all(plan.currency == "LSL" for plan in plans)

    tenant = Tenant(name="Phase 13 Operations Verification", slug=f"phase13-ops-{uuid.uuid4().hex[:12]}")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == "business"))
    assert plan is not None
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.active, 30)

    snapshot = capture_usage(db, tenant.id, subscription.current_period_start, subscription.current_period_end)
    assert snapshot.mailboxes == 0 and snapshot.domains == 0 and snapshot.storage_bytes == 0
    assert snapshot.period_start == subscription.current_period_start
    assert snapshot.period_end == subscription.current_period_end

    invoice = generate_invoice(db, tenant.id, due_days=14)
    invoice_again = generate_invoice(db, tenant.id, due_days=14)
    assert invoice_again.id == invoice.id, "invoice generation must be idempotent per billing period"
    assert invoice.total_minor == plan.monthly_price_minor
    assert invoice.usage_snapshot_id is not None
    assert invoice.period_start == subscription.current_period_start
    assert invoice.period_end == subscription.current_period_end

    decision = entitlement_decision(db, tenant.id, "domain")
    assert decision["allowed"] is True

    secret = "phase13-verification-webhook-secret-1234567890"
    sample = b'{"event_id":"sig-test"}'
    import hashlib, hmac
    signature = hmac.new(secret.encode(), sample, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(sample, signature, secret) is True
    assert verify_webhook_signature(sample, "bad", secret) is False

    failed_payload = {
        "event_id": f"failed-{uuid.uuid4().hex}",
        "event_type": "invoice.payment_failed",
        "tenant_id": str(tenant.id),
        "invoice_id": str(invoice.id),
    }
    failed_raw = json.dumps(failed_payload, sort_keys=True).encode()
    failed_event, duplicate = process_payment_event(
        db,
        "verification",
        failed_payload["event_id"],
        failed_payload["event_type"],
        failed_payload,
        failed_raw,
        True,
        grace_days=7,
    )
    assert duplicate is False and failed_event.processed is True
    db.refresh(subscription)
    assert subscription.status == SubscriptionStatus.past_due
    assert subscription.past_due_since is not None and subscription.grace_ends_at is not None
    assert entitlement_decision(db, tenant.id, "domain")["allowed"] is True, "grace must be non-destructive"

    duplicate_event, duplicate = process_payment_event(
        db,
        "verification",
        failed_payload["event_id"],
        failed_payload["event_type"],
        failed_payload,
        failed_raw,
        True,
        grace_days=7,
    )
    assert duplicate is True and duplicate_event.id == failed_event.id

    subscription.grace_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    denied = entitlement_decision(db, tenant.id, "domain")
    assert denied["allowed"] is False
    assert "grace" in denied["reason"].lower()

    paid_payload = {
        "event_id": f"paid-{uuid.uuid4().hex}",
        "event_type": "invoice.paid",
        "tenant_id": str(tenant.id),
        "invoice_id": str(invoice.id),
    }
    paid_raw = json.dumps(paid_payload, sort_keys=True).encode()
    paid_event, duplicate = process_payment_event(
        db,
        "verification",
        paid_payload["event_id"],
        paid_payload["event_type"],
        paid_payload,
        paid_raw,
        True,
        grace_days=7,
    )
    assert duplicate is False and paid_event.processed is True
    db.refresh(subscription)
    db.refresh(invoice)
    assert subscription.status == SubscriptionStatus.active
    assert subscription.past_due_since is None and subscription.grace_ends_at is None
    assert invoice.status.value == "paid" and invoice.paid_at is not None

    summary = billing_summary(db, tenant.id)
    assert summary["subscription"]["plan_code"] == "business"
    assert summary["subscription"]["status"] == "active"
    assert summary["within_plan"] is True

    for event in db.scalars(select(BillingPaymentEvent).where(BillingPaymentEvent.tenant_id == tenant.id)).all():
        db.delete(event)
    db.delete(tenant)
    db.commit()

print("billing schema, invoices, signed-event primitive, idempotency, dunning, grace, and entitlement decisions verified")
PY

printf '\n== Phase 13: API surface and enforcement wiring ==\n'
$COMPOSE exec -T backend python - <<'PY'
import httpx

with httpx.Client(base_url='http://127.0.0.1:8000', timeout=5) as client:
    spec = client.get('/openapi.json').json()
paths = spec['paths']
required = {
    '/api/v1/billing/plans',
    '/api/v1/tenants/{tenant_id}/billing/summary',
    '/api/v1/tenants/{tenant_id}/billing/entitlements/{resource}',
    '/api/v1/tenants/{tenant_id}/billing/usage/snapshot',
    '/api/v1/tenants/{tenant_id}/billing/subscription',
    '/api/v1/tenants/{tenant_id}/billing/invoices',
    '/api/v1/billing/webhooks/{provider}',
}
missing = required - set(paths)
assert not missing, missing
print('billing operations API routes registered')
PY

grep -q 'billing.read' apps/backend/app/core/rbac.py
grep -q 'billing.manage' apps/backend/app/core/rbac.py
grep -q 'require_entitlement(db, tenant_id, "domain")' apps/backend/app/api/v1/domains.py
grep -q 'BILLING_WEBHOOK_SECRET' .env.example
grep -q 'billing_payment_events' apps/backend/alembic/versions/0007_billing_operations.py
grep -q 'Idempotent invoice generation' docs/PHASE-13-SAAS-BILLING.md

printf '\nPhase 13 BILLING OPERATIONS verification PASSED.\n'
printf 'Verified full Phase 12 regression, historical billing migration 0007, current Alembic head, billing-period invoice generation, payment-event idempotency, HMAC signature primitive, dunning grace, non-destructive entitlement decisions, domain enforcement, and billing operations API surface.\n'
printf 'Commercial release layers may advance Alembic beyond 0007 while this historical Phase 13 gate remains valid.\n'