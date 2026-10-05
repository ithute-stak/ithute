from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import BillingAddon, BillingPlan, TenantAddon, TenantSubscription


RESOURCE_FIELDS = {
    "mailboxes": "included_mailboxes",
    "domains": "included_domains",
    "mail_storage_mb": "included_storage_mb",
    "api_keys": "max_api_keys",
    "hosted_projects": "included_hosted_projects",
    "hosting_storage_mb": "hosting_storage_mb",
    "database_count": "hosting_database_limit",
    "database_storage_mb": "hosting_database_storage_mb",
    "source_storage_mb": "hosting_source_storage_mb",
}

_COPY_FIELDS = (
    "currency",
    "included_mailboxes",
    "included_domains",
    "included_storage_mb",
    "max_api_keys",
    "allow_metered_overages",
    "overage_mailbox_minor",
    "overage_domain_minor",
    "overage_storage_gb_minor",
    "overage_api_key_minor",
    "overage_hosted_project_minor",
    "overage_hosting_storage_gb_minor",
    "overage_database_minor",
    "overage_database_storage_gb_minor",
    "overage_source_storage_gb_minor",
    "included_hosted_projects",
    "hosting_storage_mb",
    "hosting_memory_mb_per_project",
    "hosting_cpu_millicores_per_project",
    "hosting_pids_per_project",
    "hosting_database_limit",
    "hosting_database_storage_mb",
    "hosting_source_storage_mb",
    "product_category",
    "description",
    "website_pages",
    "includes_website_design",
    "includes_logo_design",
    "includes_brand_guide",
    "includes_company_profile",
    "includes_letterhead",
    "includes_page_headers_footers",
    "includes_business_templates",
    "included_revisions",
    "content_updates_per_month",
    "support_level",
    "minimum_term_months",
    "price_from",
)


def _base_plan_id(db: Session, subscription: TenantSubscription) -> UUID:
    value = db.execute(
        text("SELECT base_plan_id FROM tenant_subscriptions WHERE id = :id"),
        {"id": str(subscription.id)},
    ).scalar_one_or_none()
    if value is None:
        value = subscription.plan_id
        db.execute(
            text("UPDATE tenant_subscriptions SET base_plan_id = :base WHERE id = :id"),
            {"base": str(value), "id": str(subscription.id)},
        )
    return UUID(str(value))


def active_addon_totals(db: Session, tenant_id: UUID) -> tuple[dict[str, int], int, int | None, list[dict]]:
    rows = db.execute(
        select(TenantAddon, BillingAddon)
        .join(BillingAddon, BillingAddon.id == TenantAddon.addon_id)
        .where(
            TenantAddon.tenant_id == tenant_id,
            TenantAddon.status == "active",
            BillingAddon.is_active.is_(True),
        )
    ).all()
    totals: dict[str, int] = defaultdict(int)
    monthly = 0
    annual: int | None = 0
    details: list[dict] = []
    for assignment, addon in rows:
        amount = addon.amount_per_quantity * assignment.quantity
        totals[addon.resource_key] += amount
        monthly += addon.monthly_price_minor * assignment.quantity
        if addon.annual_price_minor is None:
            annual = None
        elif annual is not None:
            annual += addon.annual_price_minor * assignment.quantity
        details.append({
            "code": addon.code,
            "name": addon.name,
            "resource_key": addon.resource_key,
            "amount": amount,
            "quantity": assignment.quantity,
        })
    return dict(totals), monthly, annual, details


def rebuild_effective_plan(db: Session, tenant_id: UUID) -> BillingPlan | None:
    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
    if subscription is None:
        return None
    base_id = _base_plan_id(db, subscription)
    base = db.get(BillingPlan, base_id)
    if base is None:
        raise RuntimeError("Subscription base package no longer exists")

    totals, addon_monthly, addon_annual, _details = active_addon_totals(db, tenant_id)
    if not totals:
        subscription.plan_id = base.id
        db.flush()
        return base

    code = f"effective-{tenant_id.hex[:32]}"
    effective = db.scalar(select(BillingPlan).where(BillingPlan.code == code))
    if effective is None:
        effective = BillingPlan(
            code=code,
            name=f"{base.name} + add-ons",
            currency=base.currency,
            monthly_price_minor=base.monthly_price_minor,
            annual_price_minor=base.annual_price_minor,
            setup_fee_minor=base.setup_fee_minor,
            included_mailboxes=base.included_mailboxes,
            included_domains=base.included_domains,
            included_storage_mb=base.included_storage_mb,
            max_api_keys=base.max_api_keys,
            allow_metered_overages=base.allow_metered_overages,
            overage_mailbox_minor=base.overage_mailbox_minor,
            overage_domain_minor=base.overage_domain_minor,
            overage_storage_gb_minor=base.overage_storage_gb_minor,
            overage_api_key_minor=base.overage_api_key_minor,
            overage_hosted_project_minor=base.overage_hosted_project_minor,
            overage_hosting_storage_gb_minor=base.overage_hosting_storage_gb_minor,
            overage_database_minor=base.overage_database_minor,
            overage_database_storage_gb_minor=base.overage_database_storage_gb_minor,
            overage_source_storage_gb_minor=base.overage_source_storage_gb_minor,
            included_hosted_projects=base.included_hosted_projects,
            hosting_storage_mb=base.hosting_storage_mb,
            hosting_memory_mb_per_project=base.hosting_memory_mb_per_project,
            hosting_cpu_millicores_per_project=base.hosting_cpu_millicores_per_project,
            hosting_pids_per_project=base.hosting_pids_per_project,
            hosting_database_limit=base.hosting_database_limit,
            hosting_database_storage_mb=base.hosting_database_storage_mb,
            hosting_source_storage_mb=base.hosting_source_storage_mb,
            product_category=base.product_category,
            description=base.description,
            website_pages=base.website_pages,
            includes_website_design=base.includes_website_design,
            includes_logo_design=base.includes_logo_design,
            includes_brand_guide=base.includes_brand_guide,
            includes_company_profile=base.includes_company_profile,
            includes_letterhead=base.includes_letterhead,
            includes_page_headers_footers=base.includes_page_headers_footers,
            includes_business_templates=base.includes_business_templates,
            included_revisions=base.included_revisions,
            content_updates_per_month=base.content_updates_per_month,
            support_level=base.support_level,
            minimum_term_months=base.minimum_term_months,
            price_from=base.price_from,
            customer_visible=False,
            featured=False,
            sort_order=9999,
            is_active=True,
        )
        db.add(effective)
        db.flush()

    effective.name = f"{base.name} + add-ons"
    for field in _COPY_FIELDS:
        setattr(effective, field, getattr(base, field))
    effective.monthly_price_minor = base.monthly_price_minor + addon_monthly
    if base.annual_price_minor is None or addon_annual is None:
        effective.annual_price_minor = None
    else:
        effective.annual_price_minor = base.annual_price_minor + addon_annual
    effective.setup_fee_minor = base.setup_fee_minor
    effective.customer_visible = False
    effective.featured = False
    effective.is_active = True

    for resource_key, amount in totals.items():
        field = RESOURCE_FIELDS.get(resource_key)
        if field:
            setattr(effective, field, int(getattr(base, field)) + int(amount))

    subscription.plan_id = effective.id
    db.flush()
    return effective


def entitlement_summary(db: Session, tenant_id: UUID) -> dict:
    subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id))
    if subscription is None:
        return {"subscription": None, "base_plan": None, "effective_plan": None, "active_addons": []}
    base_id = _base_plan_id(db, subscription)
    base = db.get(BillingPlan, base_id)
    effective = db.get(BillingPlan, subscription.plan_id)
    _totals, _monthly, _annual, details = active_addon_totals(db, tenant_id)

    def compact(plan: BillingPlan | None) -> dict | None:
        if plan is None:
            return None
        return {
            "id": str(plan.id),
            "code": plan.code,
            "name": plan.name,
            "monthly_price_minor": plan.monthly_price_minor,
            "annual_price_minor": plan.annual_price_minor,
            "included_mailboxes": plan.included_mailboxes,
            "included_domains": plan.included_domains,
            "included_storage_mb": plan.included_storage_mb,
            "allow_metered_overages": plan.allow_metered_overages,
            "overage_mailbox_minor": plan.overage_mailbox_minor,
            "overage_domain_minor": plan.overage_domain_minor,
            "overage_storage_gb_minor": plan.overage_storage_gb_minor,
            "overage_api_key_minor": plan.overage_api_key_minor,
            "overage_hosted_project_minor": plan.overage_hosted_project_minor,
            "overage_hosting_storage_gb_minor": plan.overage_hosting_storage_gb_minor,
            "overage_database_minor": plan.overage_database_minor,
            "overage_database_storage_gb_minor": plan.overage_database_storage_gb_minor,
            "overage_source_storage_gb_minor": plan.overage_source_storage_gb_minor,
            "included_hosted_projects": plan.included_hosted_projects,
            "hosting_storage_mb": plan.hosting_storage_mb,
            "hosting_database_limit": plan.hosting_database_limit,
            "hosting_database_storage_mb": plan.hosting_database_storage_mb,
            "hosting_source_storage_mb": plan.hosting_source_storage_mb,
        }

    return {
        "subscription": {"id": str(subscription.id), "status": subscription.status.value},
        "base_plan": compact(base),
        "effective_plan": compact(effective),
        "active_addons": details,
    }
