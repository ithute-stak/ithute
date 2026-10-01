from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_platform_owner
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import get_db
from app.models import (
    AuditLog,
    BillingPlan,
    CustomerProfile,
    MembershipRole,
    Notification,
    SubscriptionStatus,
    Tenant,
    TenantMembership,
    TenantSubscription,
    User,
)
from app.services.billing import assign_subscription, ensure_default_plans
from app.services.signup_security import enforce_signup_rate_limit, ensure_public_signup_open, send_system_email

router = APIRouter(tags=["customer-applications"])


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:80]


class CustomerApplicationCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=150)
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    plan_code: str = Field(default="business", min_length=2, max_length=50)
    phone: str | None = Field(default=None, max_length=60)
    terms_accepted: bool


class RejectApplication(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _primary_applicant(db: Session, tenant_id: UUID) -> tuple[TenantMembership | None, User | None]:
    membership = db.scalar(
        select(TenantMembership)
        .where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.role == MembershipRole.tenant_admin,
        )
        .order_by(TenantMembership.created_at.asc())
    )
    return membership, db.get(User, membership.user_id) if membership else None


def _application_out(db: Session, tenant: Tenant) -> dict:
    _membership, user = _primary_applicant(db, tenant.id)
    if tenant.rejected_at is not None:
        state = "rejected"
    elif tenant.approved_at is not None and not tenant.requires_approval:
        state = "approved"
    else:
        state = "pending"
    return {
        "tenant_id": str(tenant.id),
        "company_name": tenant.name,
        "slug": tenant.slug,
        "status": state,
        "requested_plan_code": tenant.requested_plan_code,
        "applicant": {
            "user_id": str(user.id) if user else None,
            "full_name": user.full_name if user else None,
            "email": user.email if user else None,
            "email_verified": bool(user and user.email_verified_at),
        },
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "approved_at": tenant.approved_at.isoformat() if tenant.approved_at else None,
        "rejected_at": tenant.rejected_at.isoformat() if tenant.rejected_at else None,
        "rejection_reason": tenant.rejection_reason,
    }


def _create_application(payload: CustomerApplicationCreate, db: Session) -> dict:
    if not payload.terms_accepted:
        raise HTTPException(status_code=422, detail="Terms of Service and Acceptable Use Policy must be accepted")

    email = str(payload.email).strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account already exists for this email")

    ensure_default_plans(db)
    plan_code = payload.plan_code.strip().lower()
    plan = db.scalar(select(BillingPlan).where(BillingPlan.code == plan_code, BillingPlan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status_code=404, detail="Selected plan is unavailable")

    slug = _slug(payload.company_name)
    if not slug:
        raise HTTPException(status_code=422, detail="Unable to create a company slug")
    if db.scalar(select(Tenant).where(Tenant.slug == slug)):
        slug = f"{slug[:68]}-{uuid4().hex[:8]}"

    tenant = Tenant(
        name=payload.company_name.strip(),
        slug=slug,
        requested_plan_code=plan.code,
        requires_approval=True,
        approved_by_user_id=None,
        rejected_at=None,
        rejection_reason=None,
    )
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        is_active=True,
    )
    db.add_all([tenant, user])
    db.flush()
    # Tenant defaults keep operator-created organizations active. Public signup is
    # the deliberate exception: clear approval after INSERT so the row is
    # unambiguously pending regardless of ORM/server default behavior.
    tenant.approved_at = None
    tenant.requires_approval = True
    db.flush()

    db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role=MembershipRole.tenant_admin))
    db.add(CustomerProfile(tenant_id=tenant.id, billing_email=email, phone=payload.phone, country="Lesotho"))
    db.add(
        Notification(
            tenant_id=tenant.id,
            user_id=user.id,
            category="onboarding",
            severity="info",
            title="Application received",
            message="Your company application is awaiting Ithute administrator approval. Your trial starts only after approval.",
            action_url="/dashboard",
        )
    )
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            actor_user_id=user.id,
            action="customer.application.create",
            resource_type="tenant",
            resource_id=str(tenant.id),
        )
    )
    db.commit()
    db.refresh(tenant)

    return {
        "created": True,
        "approval_status": "pending",
        "tenant": {"id": str(tenant.id), "name": tenant.name, "slug": tenant.slug},
        "user": {"id": str(user.id), "email": user.email, "full_name": user.full_name},
        "requested_plan": plan.code,
        "login_url": "/login",
    }


@router.post("/public/customer-applications", status_code=201)
def create_customer_application(
    payload: CustomerApplicationCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    ensure_public_signup_open()
    enforce_signup_rate_limit(request)
    return _create_application(payload, db)


@router.post("/public/signup", status_code=201, include_in_schema=False)
def legacy_public_signup(payload: CustomerApplicationCreate, db: Session = Depends(get_db)):
    # Registered before the historical instant-trial route. The global middleware
    # already applies domain/readiness checks and rate limiting to /public/signup.
    return _create_application(payload, db)


@router.get("/platform/customer-applications")
def list_customer_applications(
    status_filter: str = Query(default="pending", alias="status", pattern="^(pending|approved|rejected|all)$"),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    query = select(Tenant).where(Tenant.requested_plan_code.is_not(None))
    if status_filter == "pending":
        query = query.where(Tenant.requires_approval.is_(True), Tenant.rejected_at.is_(None))
    elif status_filter == "approved":
        query = query.where(Tenant.requires_approval.is_(False), Tenant.approved_at.is_not(None), Tenant.rejected_at.is_(None))
    elif status_filter == "rejected":
        query = query.where(Tenant.rejected_at.is_not(None))
    rows = db.scalars(query.order_by(Tenant.created_at.desc()).limit(500)).all()
    return {"items": [_application_out(db, row) for row in rows]}


@router.post("/platform/customer-applications/{tenant_id}/approve")
def approve_customer_application(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None or tenant.requested_plan_code is None:
        raise HTTPException(status_code=404, detail="Customer application not found")
    if tenant.rejected_at is not None:
        raise HTTPException(status_code=409, detail="Rejected applications cannot be approved")

    existing_subscription = db.scalar(select(TenantSubscription).where(TenantSubscription.tenant_id == tenant.id))
    if tenant.approved_at is not None and not tenant.requires_approval:
        if existing_subscription is None:
            raise HTTPException(status_code=409, detail="Approved customer has no subscription; manual repair required")
        return _application_out(db, tenant)

    ensure_default_plans(db)
    plan = db.scalar(
        select(BillingPlan).where(
            BillingPlan.code == tenant.requested_plan_code,
            BillingPlan.is_active.is_(True),
        )
    )
    if plan is None:
        raise HTTPException(status_code=409, detail="Requested plan is no longer available")
    if existing_subscription is not None:
        raise HTTPException(status_code=409, detail="Pending application already has a subscription")

    tenant.approved_at = datetime.now(timezone.utc)
    tenant.approved_by_user_id = current.id
    tenant.requires_approval = False
    subscription = assign_subscription(db, tenant.id, plan, SubscriptionStatus.trialing, period_days=14)
    _membership, applicant = _primary_applicant(db, tenant.id)
    if applicant:
        db.add(
            Notification(
                tenant_id=tenant.id,
                user_id=applicant.id,
                category="onboarding",
                severity="success",
                title="Your Ithute company has been approved",
                message="Your 14-day trial is now active. You can start configuring your services.",
                action_url="/dashboard",
            )
        )
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            actor_user_id=current.id,
            action="customer.application.approve",
            resource_type="tenant",
            resource_id=str(tenant.id),
        )
    )
    db.commit()
    db.refresh(tenant)

    if applicant:
        try:
            send_system_email(
                applicant.email,
                "Your Ithute company account has been approved",
                f"Hello {applicant.full_name},\n\n"
                f"{tenant.name} has been approved on Ithute. Your 14-day trial starts now.\n\n"
                f"Sign in at {settings.frontend_url.rstrip('/')}/login to continue.\n",
            )
        except Exception:
            pass

    result = _application_out(db, tenant)
    result["subscription"] = {
        "plan": plan.code,
        "status": subscription.status.value,
        "trial_ends_at": subscription.current_period_end.isoformat(),
    }
    return result


@router.post("/platform/customer-applications/{tenant_id}/reject")
def reject_customer_application(
    tenant_id: UUID,
    payload: RejectApplication,
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if tenant is None or tenant.requested_plan_code is None:
        raise HTTPException(status_code=404, detail="Customer application not found")
    if tenant.approved_at is not None and not tenant.requires_approval:
        raise HTTPException(status_code=409, detail="An approved customer cannot be rejected from the application queue")

    tenant.requires_approval = True
    tenant.approved_at = None
    tenant.approved_by_user_id = None
    tenant.rejected_at = datetime.now(timezone.utc)
    tenant.rejection_reason = payload.reason.strip()
    _membership, applicant = _primary_applicant(db, tenant.id)
    if applicant:
        db.add(
            Notification(
                tenant_id=tenant.id,
                user_id=applicant.id,
                category="onboarding",
                severity="warning",
                title="Ithute application update",
                message=f"Your company application was not approved: {tenant.rejection_reason}",
                action_url="/dashboard",
            )
        )
    db.add(
        AuditLog(
            tenant_id=tenant.id,
            actor_user_id=current.id,
            action="customer.application.reject",
            resource_type="tenant",
            resource_id=str(tenant.id),
            metadata_json=json.dumps({"reason": tenant.rejection_reason}, sort_keys=True),
        )
    )
    db.commit()
    db.refresh(tenant)
    return _application_out(db, tenant)


@router.get("/me/customer-application")
def my_customer_application(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    membership = db.scalar(
        select(TenantMembership)
        .where(TenantMembership.user_id == current.id, TenantMembership.role == MembershipRole.tenant_admin)
        .order_by(TenantMembership.created_at.asc())
    )
    if membership is None:
        return {"application": None}
    tenant = db.get(Tenant, membership.tenant_id)
    if tenant is None or tenant.requested_plan_code is None:
        return {"application": None}
    return {"application": _application_out(db, tenant)}
