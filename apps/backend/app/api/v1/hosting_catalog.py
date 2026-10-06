from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner, require_tenant_permission
from app.db.session import get_db
from app.models import AuditLog, BillingAddon, BillingPlan, TenantAddon, TenantSubscription, User
from app.services.catalog_entitlements import RESOURCE_FIELDS, entitlement_summary, rebuild_effective_plan

router = APIRouter(tags=["hosting-catalog"])
_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")
_SUPPORT = {"standard", "priority", "dedicated"}


class PlanPayload(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    currency: str = "LSL"
    monthly_price_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    annual_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    setup_fee_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    included_mailboxes: int = Field(default=18, ge=0, le=1_000_000)
    included_domains: int = Field(default=1, ge=1, le=100_000)
    included_storage_mb: int = Field(default=36_864, ge=0, le=20_000_000)
    max_api_keys: int = Field(default=3, ge=0, le=100_000)
    included_hosted_projects: int = Field(default=1, ge=0, le=10_000)
    hosting_storage_mb: int = Field(default=2048, ge=0, le=2_000_000)
    hosting_memory_mb_per_project: int = Field(default=512, ge=0, le=65_536)
    hosting_cpu_millicores_per_project: int = Field(default=500, ge=0, le=32_000)
    hosting_pids_per_project: int = Field(default=128, ge=0, le=32_768)
    hosting_database_limit: int = Field(default=2, ge=0, le=100_000)
    hosting_database_storage_mb: int = Field(default=2048, ge=0, le=2_000_000)
    hosting_source_storage_mb: int = Field(default=2048, ge=0, le=2_000_000)
    product_category: str = Field(default="Website & Application Hosting", min_length=2, max_length=80)
    support_level: str = Field(default="standard", min_length=2, max_length=40)
    minimum_term_months: int = Field(default=12, ge=0, le=60)
    price_from: bool = False
    customer_visible: bool = True
    featured: bool = False
    sort_order: int = Field(default=100, ge=0, le=100_000)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip().lower()
        if not _CODE_RE.fullmatch(value):
            raise ValueError("Package code may contain lowercase letters, numbers and hyphens only")
        return value

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if value != "LSL":
            raise ValueError("Hosting packages are currently priced in LSL")
        return value

    @field_validator("support_level")
    @classmethod
    def validate_support(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in _SUPPORT:
            raise ValueError("Support level must be standard, priority or dedicated")
        return value


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    monthly_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    annual_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    setup_fee_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    included_mailboxes: int | None = Field(default=None, ge=0, le=1_000_000)
    included_domains: int | None = Field(default=None, ge=1, le=100_000)
    included_storage_mb: int | None = Field(default=None, ge=0, le=20_000_000)
    max_api_keys: int | None = Field(default=None, ge=0, le=100_000)
    included_hosted_projects: int | None = Field(default=None, ge=0, le=10_000)
    hosting_storage_mb: int | None = Field(default=None, ge=0, le=2_000_000)
    hosting_memory_mb_per_project: int | None = Field(default=None, ge=0, le=65_536)
    hosting_cpu_millicores_per_project: int | None = Field(default=None, ge=0, le=32_000)
    hosting_pids_per_project: int | None = Field(default=None, ge=0, le=32_768)
    hosting_database_limit: int | None = Field(default=None, ge=0, le=100_000)
    hosting_database_storage_mb: int | None = Field(default=None, ge=0, le=2_000_000)
    hosting_source_storage_mb: int | None = Field(default=None, ge=0, le=2_000_000)
    product_category: str | None = Field(default=None, min_length=2, max_length=80)
    support_level: str | None = None
    minimum_term_months: int | None = Field(default=None, ge=0, le=60)
    price_from: bool | None = None
    customer_visible: bool | None = None
    featured: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100_000)
    is_active: bool | None = None

    @field_validator("support_level")
    @classmethod
    def validate_support(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if value not in _SUPPORT:
            raise ValueError("Support level must be standard, priority or dedicated")
        return value


class AddonPayload(BaseModel):
    code: str = Field(min_length=2, max_length=60)
    name: str = Field(min_length=2, max_length=140)
    description: str = Field(default="", max_length=500)
    monthly_price_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    annual_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    setup_fee_minor: int = Field(default=0, ge=0, le=2_000_000_000)
    resource_key: str
    amount_per_quantity: int = Field(gt=0, le=20_000_000)
    unit_label: str = Field(min_length=1, max_length=40)
    max_quantity: int = Field(default=100, ge=1, le=100_000)
    customer_visible: bool = True
    is_active: bool = True
    sort_order: int = Field(default=100, ge=0, le=100_000)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip().lower()
        if not _CODE_RE.fullmatch(value):
            raise ValueError("Add-on code may contain lowercase letters, numbers and hyphens only")
        return value

    @field_validator("resource_key")
    @classmethod
    def validate_resource(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in RESOURCE_FIELDS:
            raise ValueError(f"resource_key must be one of: {', '.join(sorted(RESOURCE_FIELDS))}")
        return value


class AddonPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=500)
    monthly_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    annual_price_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    setup_fee_minor: int | None = Field(default=None, ge=0, le=2_000_000_000)
    amount_per_quantity: int | None = Field(default=None, gt=0, le=20_000_000)
    unit_label: str | None = Field(default=None, min_length=1, max_length=40)
    max_quantity: int | None = Field(default=None, ge=1, le=100_000)
    customer_visible: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=100_000)


class AddonRequest(BaseModel):
    quantity: int = Field(default=1, ge=1, le=100_000)


def _plan_out(plan: BillingPlan) -> dict:
    return {
        "id": str(plan.id), "code": plan.code, "name": plan.name,
        "description": plan.description, "currency": plan.currency,
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
        "support_level": plan.support_level,
        "minimum_term_months": plan.minimum_term_months,
        "price_from": plan.price_from,
        "customer_visible": plan.customer_visible,
        "featured": plan.featured,
        "sort_order": plan.sort_order,
        "is_active": plan.is_active,
    }


def _addon_out(addon: BillingAddon) -> dict:
    return {
        "id": str(addon.id), "code": addon.code, "name": addon.name,
        "description": addon.description, "currency": addon.currency,
        "monthly_price_minor": addon.monthly_price_minor,
        "annual_price_minor": addon.annual_price_minor,
        "setup_fee_minor": addon.setup_fee_minor,
        "resource_key": addon.resource_key,
        "amount_per_quantity": addon.amount_per_quantity,
        "unit_label": addon.unit_label,
        "max_quantity": addon.max_quantity,
        "customer_visible": addon.customer_visible,
        "is_active": addon.is_active, "sort_order": addon.sort_order,
    }


def _assignment_out(row: TenantAddon, addon: BillingAddon) -> dict:
    result = _addon_out(addon)
    result.update({
        "assignment_id": str(row.id), "quantity": row.quantity, "status": row.status,
        "requested_at": row.requested_at.isoformat() if row.requested_at else None,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
    })
    return result


def _audit(db: Session, actor: User, action: str, resource_type: str, resource_id: str, metadata: dict | None = None, tenant_id: UUID | None = None) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id, actor_user_id=actor.id, action=action,
        resource_type=resource_type, resource_id=resource_id,
        metadata_json=json.dumps(metadata or {}, sort_keys=True),
    ))


def _rebuild_subscribers(db: Session, plan_id: UUID) -> None:
    tenant_ids = set(db.scalars(select(TenantSubscription.tenant_id).where(TenantSubscription.plan_id == plan_id)).all())
    tenant_ids.update(UUID(str(value)) for value in db.execute(
        text("SELECT tenant_id FROM tenant_subscriptions WHERE base_plan_id = :plan"), {"plan": str(plan_id)}
    ).scalars().all())
    for tenant_id in tenant_ids:
        rebuild_effective_plan(db, tenant_id)


# Compatibility implementation retained for internal reuse; canonical_pricing owns GET /public/pricing.
def public_pricing(db: Session = Depends(get_db)):
    plans = db.scalars(select(BillingPlan).where(
        BillingPlan.is_active.is_(True), BillingPlan.customer_visible.is_(True)
    ).order_by(BillingPlan.sort_order, BillingPlan.monthly_price_minor, BillingPlan.name)).all()
    return {"currency": "LSL", "items": [_plan_out(plan) for plan in plans]}


@router.get("/public/addons")
def public_addons(db: Session = Depends(get_db)):
    rows = db.scalars(select(BillingAddon).where(
        BillingAddon.is_active.is_(True), BillingAddon.customer_visible.is_(True)
    ).order_by(BillingAddon.sort_order, BillingAddon.name)).all()
    return {"currency": "LSL", "items": [_addon_out(row) for row in rows]}


# Compatibility implementation retained for internal reuse; plan_admin owns GET /platform/billing/plans.
def owner_plans(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    rows = db.scalars(select(BillingPlan).where(~BillingPlan.code.like("effective-%")).order_by(BillingPlan.sort_order, BillingPlan.name)).all()
    return {"items": [_plan_out(row) for row in rows]}


# Compatibility implementation retained for internal reuse; plan_admin owns POST /platform/billing/plans.
def owner_create_plan(payload: PlanPayload, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    if db.scalar(select(BillingPlan).where(BillingPlan.code == payload.code)):
        raise HTTPException(409, "A package with this code already exists")
    values = payload.model_dump()
    plan = BillingPlan(**values)
    db.add(plan); db.flush()
    _audit(db, current, "billing.plan.create", "billing_plan", str(plan.id), {"code": plan.code})
    db.commit(); db.refresh(plan)
    return _plan_out(plan)


# Compatibility implementation retained for internal reuse; plan_admin owns PATCH /platform/billing/plans/{plan_id}.
def owner_update_plan(plan_id: UUID, payload: PlanPatch, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    plan = db.get(BillingPlan, plan_id)
    if plan is None or plan.code.startswith("effective-"):
        raise HTTPException(404, "Package not found")
    changes = payload.model_dump(exclude_unset=True)
    before = _plan_out(plan)
    for key, value in changes.items(): setattr(plan, key, value)
    _audit(db, current, "billing.plan.update", "billing_plan", str(plan.id), {"before": before, "changed_fields": sorted(changes)})
    db.flush(); _rebuild_subscribers(db, plan.id); db.commit(); db.refresh(plan)
    return _plan_out(plan)


@router.get("/platform/billing/addons")
def owner_addons(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    rows = db.scalars(select(BillingAddon).order_by(BillingAddon.sort_order, BillingAddon.name)).all()
    return {"items": [_addon_out(row) for row in rows]}


@router.post("/platform/billing/addons", status_code=status.HTTP_201_CREATED)
def owner_create_addon(payload: AddonPayload, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    if db.scalar(select(BillingAddon).where(BillingAddon.code == payload.code)):
        raise HTTPException(409, "An add-on with this code already exists")
    addon = BillingAddon(currency="LSL", **payload.model_dump())
    db.add(addon); db.flush()
    _audit(db, current, "billing.addon.create", "billing_addon", str(addon.id), {"code": addon.code, "resource_key": addon.resource_key})
    db.commit(); db.refresh(addon)
    return _addon_out(addon)


@router.patch("/platform/billing/addons/{addon_id}")
def owner_update_addon(addon_id: UUID, payload: AddonPatch, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    addon = db.get(BillingAddon, addon_id)
    if addon is None: raise HTTPException(404, "Add-on not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items(): setattr(addon, key, value)
    _audit(db, current, "billing.addon.update", "billing_addon", str(addon.id), {"changed_fields": sorted(changes)})
    db.flush()
    tenants = db.scalars(select(TenantAddon.tenant_id).where(TenantAddon.addon_id == addon.id, TenantAddon.status == "active")).all()
    for tenant_id in set(tenants): rebuild_effective_plan(db, tenant_id)
    db.commit(); db.refresh(addon)
    return _addon_out(addon)


@router.get("/tenants/{tenant_id}/addons")
def tenant_addons(tenant_id: UUID, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.read", db, current)
    catalog = db.scalars(select(BillingAddon).where(BillingAddon.is_active.is_(True), BillingAddon.customer_visible.is_(True)).order_by(BillingAddon.sort_order, BillingAddon.name)).all()
    assigned = db.execute(select(TenantAddon, BillingAddon).join(BillingAddon, BillingAddon.id == TenantAddon.addon_id).where(TenantAddon.tenant_id == tenant_id)).all()
    return {
        "catalog": [_addon_out(row) for row in catalog],
        "assignments": [_assignment_out(assignment, addon) for assignment, addon in assigned],
        "entitlements": entitlement_summary(db, tenant_id),
    }


@router.post("/tenants/{tenant_id}/addons/{addon_id}/request", status_code=status.HTTP_201_CREATED)
def request_addon(tenant_id: UUID, addon_id: UUID, payload: AddonRequest, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    require_tenant_permission(tenant_id, "billing.manage", db, current)
    addon = db.get(BillingAddon, addon_id)
    if addon is None or not addon.is_active or not addon.customer_visible: raise HTTPException(404, "Add-on is unavailable")
    if payload.quantity > addon.max_quantity: raise HTTPException(422, f"Maximum quantity is {addon.max_quantity}")
    row = db.scalar(select(TenantAddon).where(TenantAddon.tenant_id == tenant_id, TenantAddon.addon_id == addon.id))
    if row is None:
        row = TenantAddon(tenant_id=tenant_id, addon_id=addon.id, requested_by_user_id=current.id)
        db.add(row)
    row.quantity = payload.quantity; row.status = "pending"; row.requested_by_user_id = current.id; row.canceled_at = None; row.activated_at = None
    _audit(db, current, "billing.addon.request", "tenant_addon", str(row.id), {"addon": addon.code, "quantity": row.quantity}, tenant_id)
    db.commit(); db.refresh(row)
    return _assignment_out(row, addon)


@router.get("/platform/billing/addon-requests")
def owner_addon_requests(status_filter: str = Query(default="pending", alias="status"), db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    query = select(TenantAddon, BillingAddon).join(BillingAddon, BillingAddon.id == TenantAddon.addon_id)
    if status_filter != "all": query = query.where(TenantAddon.status == status_filter)
    rows = db.execute(query.order_by(TenantAddon.requested_at.desc())).all()
    return {"items": [dict(_assignment_out(assignment, addon), tenant_id=str(assignment.tenant_id)) for assignment, addon in rows]}


@router.post("/platform/billing/addon-requests/{assignment_id}/activate")
def activate_addon(assignment_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(TenantAddon, assignment_id)
    if row is None: raise HTTPException(404, "Add-on request not found")
    addon = db.get(BillingAddon, row.addon_id)
    if addon is None or not addon.is_active: raise HTTPException(409, "Add-on is not active")
    row.status = "active"; row.approved_by_user_id = current.id; row.activated_at = datetime.now(timezone.utc); row.canceled_at = None
    effective = rebuild_effective_plan(db, row.tenant_id)
    _audit(db, current, "billing.addon.activate", "tenant_addon", str(row.id), {"addon": addon.code, "quantity": row.quantity, "effective_plan": effective.code if effective else None}, row.tenant_id)
    db.commit(); db.refresh(row)
    return _assignment_out(row, addon)


@router.post("/platform/billing/addon-requests/{assignment_id}/cancel")
def cancel_addon(assignment_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    row = db.get(TenantAddon, assignment_id)
    if row is None: raise HTTPException(404, "Add-on request not found")
    addon = db.get(BillingAddon, row.addon_id)
    row.status = "canceled"; row.canceled_at = datetime.now(timezone.utc)
    effective = rebuild_effective_plan(db, row.tenant_id)
    _audit(db, current, "billing.addon.cancel", "tenant_addon", str(row.id), {"effective_plan": effective.code if effective else None}, row.tenant_id)
    db.commit(); db.refresh(row)
    return _assignment_out(row, addon)
