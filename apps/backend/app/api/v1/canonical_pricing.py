from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BillingPlan

router = APIRouter(tags=["canonical-pricing"])


def _plan_out(plan: BillingPlan) -> dict:
    return {
        "id": str(plan.id),
        "code": plan.code,
        "name": plan.name,
        "description": plan.description,
        "currency": plan.currency,
        "monthly_price_minor": plan.monthly_price_minor,
        "annual_price_minor": plan.annual_price_minor,
        "setup_fee_minor": plan.setup_fee_minor,
        "included_mailboxes": plan.included_mailboxes,
        "included_domains": plan.included_domains,
        "included_storage_mb": plan.included_storage_mb,
        "max_api_keys": plan.max_api_keys,
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
        "hosting_memory_mb_per_project": plan.hosting_memory_mb_per_project,
        "hosting_cpu_millicores_per_project": plan.hosting_cpu_millicores_per_project,
        "hosting_pids_per_project": plan.hosting_pids_per_project,
        "hosting_database_limit": plan.hosting_database_limit,
        "hosting_database_storage_mb": plan.hosting_database_storage_mb,
        "hosting_source_storage_mb": plan.hosting_source_storage_mb,
        "product_category": plan.product_category,
        "support_level": plan.support_level,
        "minimum_term_months": plan.minimum_term_months,
        "price_from": plan.price_from,
        "customer_visible": plan.customer_visible,
        "featured": plan.featured,
        "sort_order": plan.sort_order,
        "is_active": plan.is_active,
        "lifecycle_state": plan.lifecycle_state,
    }


@router.get("/public/pricing")
def public_pricing(db: Session = Depends(get_db)):
    plans = db.scalars(
        select(BillingPlan)
        .where(
            BillingPlan.is_active.is_(True),
            BillingPlan.customer_visible.is_(True),
            BillingPlan.lifecycle_state == "sellable",
            ~BillingPlan.code.like("effective-%"),
        )
        .order_by(BillingPlan.sort_order, BillingPlan.annual_price_minor, BillingPlan.monthly_price_minor, BillingPlan.name)
    ).all()
    return {"currency": "LSL", "items": [_plan_out(plan) for plan in plans]}
