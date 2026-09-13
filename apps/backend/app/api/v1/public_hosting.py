from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BillingPlan
from app.services.billing import ensure_default_plans

router = APIRouter(tags=["public-hosting"])


@router.get("/public/hosting-pricing")
def public_hosting_pricing(db: Session = Depends(get_db)):
    """Public commercial catalog including app-hosting resource limits."""
    ensure_default_plans(db)
    plans = db.scalars(
        select(BillingPlan)
        .where(BillingPlan.is_active.is_(True))
        .order_by(BillingPlan.monthly_price_minor, BillingPlan.name)
    ).all()
    return {
        "items": [
            {
                "code": plan.code,
                "name": plan.name,
                "currency": plan.currency,
                "monthly_price_minor": plan.monthly_price_minor,
                "included_mailboxes": plan.included_mailboxes,
                "included_domains": plan.included_domains,
                "included_storage_mb": plan.included_storage_mb,
                "max_api_keys": plan.max_api_keys,
                "included_hosted_projects": plan.included_hosted_projects,
                "hosting_storage_mb": plan.hosting_storage_mb,
                "hosting_memory_mb_per_project": plan.hosting_memory_mb_per_project,
                "hosting_cpu_millicores_per_project": plan.hosting_cpu_millicores_per_project,
                "hosting_pids_per_project": plan.hosting_pids_per_project,
            }
            for plan in plans
        ]
    }
