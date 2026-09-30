import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import AuditLog, BillingPlan, TenantSubscription, User
from app.services.billing import ensure_default_plans

router = APIRouter(tags=["plan-admin"])
_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,49}$")
_SUPPORT_LEVELS = {"standard", "priority", "dedicated"}


def _validate_hosting_bundle(
    *,
    projects: int,
    storage_mb: int,
    memory_mb: int,
    cpu_millicores: int,
    pids: int,
    database_limit: int,
    database_storage_mb: int,
    source_storage_mb: int,
) -> None:
    if projects == 0:
        if any((storage_mb, memory_mb, cpu_millicores, pids, database_limit, database_storage_mb, source_storage_mb)):
            raise ValueError("A package with no hosted projects must set all application-hosting limits to 0")
        return
    if not 1024 <= storage_mb <= 10240:
        raise ValueError("Application hosting storage must be between 1 GB and 10 GB per organization")
    if not 128 <= memory_mb <= 8192:
        raise ValueError("Application memory per project must be between 128 MB and 8192 MB")
    if not 100 <= cpu_millicores <= 4000:
        raise ValueError("Application CPU per project must be between 100 and 4000 millicores")
    if not 32 <= pids <= 2048:
        raise ValueError("Application process limit per project must be between 32 and 2048")
    if not 1 <= database_limit <= 2000:
        raise ValueError("Hosted database limit must be between 1 and 2000")
    if not 128 <= database_storage_mb <= 102400:
        raise ValueError("Hosted database storage must be between 128 MB and 100 GB per organization")
    if not 128 <= source_storage_mb <= 102400:
        raise ValueError("Hosted source storage must be between 128 MB and 100 GB per organization")


class CommercialFields(BaseModel):
    product_category: str = Field(default="Website & Hosting", min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    website_pages: int = Field(default=0, ge=0, le=100)
    includes_website_design: bool = False
    includes_logo_design: bool = False
    includes_brand_guide: bool = False
    includes_company_profile: bool = False
    includes_letterhead: bool = False
    includes_page_headers_footers: bool = False
    includes_business_templates: bool = False
    included_revisions: int = Field(default=0, ge=0, le=100)
    content_updates_per_month: int = Field(default=0, ge=0, le=100)
    support_level: str = Field(default="standard", min_length=2, max_length=40)
    minimum_term_months: int = Field(default=1, ge=0, le=36)
    price_from: bool = False

    @field_validator("product_category", "description", "support_level")
    @classmethod
    def normalize_commercial_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("support_level")
    @classmethod
    def validate_support_level(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in _SUPPORT_LEVELS:
            raise ValueError("support_level must be standard, priority or dedicated")
        return normalized


class PlanCreate(CommercialFields):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=120)
    currency: str = Field(default="LSL", min_length=3, max_length=3)
    monthly_price_minor: int = Field(ge=0, le=2_000_000_000)
    included_mailboxes: int = Field(default=0, ge=0, le=1_000_000)
    included_domains: int = Field(default=1, ge=1, le=100_000)
    included_storage_mb: int = Field(default=0, ge=0, le=2_000_000_000)
    max_api_keys: int = Field(default=0, ge=0, le=100_000)
    included_hosted_projects: int = Field(default=1, ge=0, le=1000)
    hosting_storage_mb: int = Field(default=1024, ge=0, le=10240)
    hosting_memory_mb_per_project: int = Field(default=512, ge=0, le=8192)
    hosting_cpu_millicores_per_project: int = Field(default=500, ge=0, le=4000)
    hosting_pids_per_project: int = Field(default=128, ge=0, le=2048)
    hosting_database_limit: int = Field(default=2, ge=0, le=2000)
    hosting_database_storage_mb: int = Field(default=1024, ge=0, le=102400)
    hosting_source_storage_mb: int = Field(default=1024, ge=0, le=102400)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _CODE_RE.fullmatch(normalized):
            raise ValueError("code may contain only lowercase letters, numbers and hyphens")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized != "LSL":
            raise ValueError("Ithute hosting packages are currently priced in LSL (Maloti)")
        return normalized

    @model_validator(mode="after")
    def validate_hosting(self):
        _validate_hosting_bundle(
            projects=self.included_hosted_projects,
            storage_mb=self.hosting_storage_mb,
            memory_mb=self.hosting_memory_mb_per_project,
            cpu_millicores=self.hosting_cpu_millicores_per_project,
            pids=self.hosting_pids_per_project,
            database_limit=self.hosting_database_limit,
            database_storage_mb=self.hosting_database_storage_mb,
            source_storage_mb=self.hosting_source_storage_mb,
        )
        return self


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    monthly_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    included_mailboxes: int | None = Field(default=None, ge=0, le=1_000_000)
    included_domains: int | None = Field(default=None, ge=1, le=100_000)
    included_storage_mb: int | None = Field(default=None, ge=0, le=2_000_000_000)
    max_api_keys: int | None = Field(default=None, ge=0, le=100_000)
    included_hosted_projects: int | None = Field(default=None, ge=0, le=1000)
    hosting_storage_mb: int | None = Field(default=None, ge=0, le=10240)
    hosting_memory_mb_per_project: int | None = Field(default=None, ge=0, le=8192)
    hosting_cpu_millicores_per_project: int | None = Field(default=None, ge=0, le=4000)
    hosting_pids_per_project: int | None = Field(default=None, ge=0, le=2048)
    hosting_database_limit: int | None = Field(default=None, ge=0, le=2000)
    hosting_database_storage_mb: int | None = Field(default=None, ge=0, le=102400)
    hosting_source_storage_mb: int | None = Field(default=None, ge=0, le=102400)
    product_category: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    website_pages: int | None = Field(default=None, ge=0, le=100)
    includes_website_design: bool | None = None
    includes_logo_design: bool | None = None
    includes_brand_guide: bool | None = None
    includes_company_profile: bool | None = None
    includes_letterhead: bool | None = None
    includes_page_headers_footers: bool | None = None
    includes_business_templates: bool | None = None
    included_revisions: int | None = Field(default=None, ge=0, le=100)
    content_updates_per_month: int | None = Field(default=None, ge=0, le=100)
    support_level: str | None = Field(default=None, min_length=2, max_length=40)
    minimum_term_months: int | None = Field(default=None, ge=0, le=36)
    price_from: bool | None = None
    is_active: bool | None = None

    @field_validator("name", "product_category", "description")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("support_level")
    @classmethod
    def validate_support_level(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in _SUPPORT_LEVELS:
            raise ValueError("support_level must be standard, priority or dedicated")
        return normalized


def _plan_out(plan: BillingPlan) -> dict:
    return {
        "id": str(plan.id),
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
        "is_active": plan.is_active,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }


def _audit(db: Session, current: User, action: str, plan: BillingPlan, metadata: dict | None = None) -> None:
    import json

    db.add(
        AuditLog(
            actor_user_id=current.id,
            action=action,
            resource_type="billing_plan",
            resource_id=str(plan.id),
            metadata_json=json.dumps(metadata or {}, sort_keys=True),
        )
    )


@router.get("/platform/billing/plans")
def list_platform_plans(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    ensure_default_plans(db)
    plans = db.scalars(select(BillingPlan).order_by(BillingPlan.monthly_price_minor, BillingPlan.name)).all()
    return {"items": [_plan_out(plan) for plan in plans]}


@router.post("/platform/billing/plans", status_code=201)
def create_platform_plan(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    ensure_default_plans(db)
    if db.scalar(select(BillingPlan).where(BillingPlan.code == payload.code)) is not None:
        raise HTTPException(status_code=409, detail="A package with this code already exists")
    plan = BillingPlan(**payload.model_dump())
    db.add(plan)
    db.flush()
    _audit(
        db,
        current,
        "billing.plan.create",
        plan,
        {
            "code": plan.code,
            "price_minor": plan.monthly_price_minor,
            "hosted_projects": plan.included_hosted_projects,
            "hosting_storage_mb": plan.hosting_storage_mb,
            "hosting_database_limit": plan.hosting_database_limit,
            "hosting_database_storage_mb": plan.hosting_database_storage_mb,
            "hosting_source_storage_mb": plan.hosting_source_storage_mb,
            "minimum_term_months": plan.minimum_term_months,
        },
    )
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)


@router.patch("/platform/billing/plans/{plan_id}")
def update_platform_plan(
    plan_id: UUID,
    payload: PlanUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    plan = db.get(BillingPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Package not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_active") is False and plan.is_active:
        subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.plan_id == plan.id).limit(1))
        if subscription is not None:
            raise HTTPException(status_code=409, detail="This package is in use by at least one tenant and cannot be deactivated")

    proposed = {
        "projects": changes.get("included_hosted_projects", plan.included_hosted_projects),
        "storage_mb": changes.get("hosting_storage_mb", plan.hosting_storage_mb),
        "memory_mb": changes.get("hosting_memory_mb_per_project", plan.hosting_memory_mb_per_project),
        "cpu_millicores": changes.get("hosting_cpu_millicores_per_project", plan.hosting_cpu_millicores_per_project),
        "pids": changes.get("hosting_pids_per_project", plan.hosting_pids_per_project),
        "database_limit": changes.get("hosting_database_limit", plan.hosting_database_limit),
        "database_storage_mb": changes.get("hosting_database_storage_mb", plan.hosting_database_storage_mb),
        "source_storage_mb": changes.get("hosting_source_storage_mb", plan.hosting_source_storage_mb),
    }
    try:
        _validate_hosting_bundle(**proposed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    before = _plan_out(plan)
    for key, value in changes.items():
        setattr(plan, key, value)
    _audit(db, current, "billing.plan.update", plan, {"before": before, "changed_fields": sorted(changes)})
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)
