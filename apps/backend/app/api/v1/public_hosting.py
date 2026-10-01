from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BillingPlan

router = APIRouter(tags=["public-hosting"])


@router.get("/public/hosting-pricing")
def public_hosting_pricing(db: Session = Depends(get_db)):
    """Public catalogue backed only by canonical sellable plans."""
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
    return {
        "currency": "LSL",
        "items": [
            {
                "code": plan.code,
                "name": plan.name,
                "currency": plan.currency,
                "monthly_price_minor": plan.monthly_price_minor,
                "annual_price_minor": plan.annual_price_minor,
                "setup_fee_minor": plan.setup_fee_minor,
                "included_mailboxes": plan.included_mailboxes,
                "included_domains": plan.included_domains,
                "included_storage_mb": plan.included_storage_mb,
                "max_api_keys": plan.max_api_keys,
                "included_hosted_projects": plan.included_hosted_projects,
                "hosting_storage_mb": plan.hosting_storage_mb,
                "hosting_memory_mb_per_project": plan.hosting_memory_mb_per_project,
                "hosting_cpu_millicores_per_project": plan.hosting_cpu_millicores_per_project,
                "hosting_pids_per_project": plan.hosting_pids_per_project,
                "hosting_database_limit": plan.hosting_database_limit,
                "hosting_database_storage_mb": plan.hosting_database_storage_mb,
                "hosting_source_storage_mb": plan.hosting_source_storage_mb,
                "product_category": plan.product_category,
                "description": plan.description,
                "website_pages": plan.website_pages,
                "includes_website_design": plan.includes_website_design,
                "includes_logo_design": plan.includes_logo_design,
                "includes_brand_guide": plan.includes_brand_guide,
                "includes_company_profile": plan.includes_company_profile,
                "includes_letterhead": plan.includes_letterhead,
                "includes_page_headers_footers": plan.includes_page_headers_footers,
                "includes_business_templates": plan.includes_business_templates,
                "included_revisions": plan.included_revisions,
                "content_updates_per_month": plan.content_updates_per_month,
                "support_level": plan.support_level,
                "minimum_term_months": plan.minimum_term_months,
                "price_from": plan.price_from,
                "featured": plan.featured,
                "sort_order": plan.sort_order,
                "lifecycle_state": plan.lifecycle_state,
            }
            for plan in plans
        ],
    }
