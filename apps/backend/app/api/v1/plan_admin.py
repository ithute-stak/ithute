import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import AuditLog, BillingPlan, TenantSubscription, User
from app.services.billing import ensure_default_plans

router = APIRouter(tags=["plan-admin"])
_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,49}$")


class PlanCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=120)
    currency: str = Field(default="LSL", min_length=3, max_length=3)
    monthly_price_minor: int = Field(ge=0, le=2_000_000_000)
    included_mailboxes: int = Field(ge=1, le=1_000_000)
    included_domains: int = Field(ge=1, le=100_000)
    included_storage_mb: int = Field(ge=100, le=2_000_000_000)
    max_api_keys: int = Field(ge=0, le=100_000)
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
            raise ValueError("Mailbox DNS packages are currently priced in LSL (Maloti)")
        return normalized


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    monthly_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    included_mailboxes: int | None = Field(default=None, ge=1, le=1_000_000)
    included_domains: int | None = Field(default=None, ge=1, le=100_000)
    included_storage_mb: int | None = Field(default=None, ge=100, le=2_000_000_000)
    max_api_keys: int | None = Field(default=None, ge=0, le=100_000)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


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
    _audit(db, current, "billing.plan.create", plan, {"code": plan.code, "price_minor": plan.monthly_price_minor})
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
    before = _plan_out(plan)
    for key, value in changes.items():
        setattr(plan, key, value)
    _audit(db, current, "billing.plan.update", plan, {"before": before, "changed_fields": sorted(changes)})
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)
