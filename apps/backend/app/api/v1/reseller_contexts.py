from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import RESELLER_DELEGATED_PERMISSIONS, get_current_user
from app.db.session import get_db
from app.models import (
    MembershipRole,
    MembershipStatus,
    ResellerAccount,
    ResellerCustomer,
    Tenant,
    TenantMembership,
    User,
)

router = APIRouter(tags=["reseller-contexts"])


def _context(
    tenant: Tenant,
    *,
    role: str,
    access_kind: str,
    membership_id: str | None = None,
    reseller_tenant_id: str | None = None,
    permissions: list[str] | None = None,
) -> dict:
    return {
        "membership_id": membership_id,
        "tenant_id": str(tenant.id),
        "tenant_name": tenant.name,
        "tenant_slug": tenant.slug,
        "tenant_status": tenant.status.value,
        "role": role,
        "status": MembershipStatus.active.value,
        "access_kind": access_kind,
        "reseller_tenant_id": reseller_tenant_id,
        "permissions": permissions or [],
    }


@router.get("/me/service-contexts")
def service_contexts(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if current.is_platform_owner:
        tenants = db.scalars(select(Tenant).order_by(Tenant.name)).all()
        return {
            "items": [
                _context(
                    tenant,
                    role="platform_owner",
                    access_kind="platform_owner",
                    permissions=["*"],
                )
                for tenant in tenants
            ]
        }

    direct_rows = db.execute(
        select(TenantMembership, Tenant)
        .join(Tenant, Tenant.id == TenantMembership.tenant_id)
        .where(
            TenantMembership.user_id == current.id,
            TenantMembership.status == MembershipStatus.active,
        )
        .order_by(Tenant.name)
    ).all()
    items = [
        _context(
            tenant,
            role=membership.role.value,
            access_kind="membership",
            membership_id=str(membership.id),
        )
        for membership, tenant in direct_rows
    ]
    known = {item["tenant_id"] for item in items}

    delegated_rows = db.execute(
        select(ResellerAccount, ResellerCustomer, Tenant)
        .join(
            TenantMembership,
            (TenantMembership.tenant_id == ResellerAccount.tenant_id)
            & (TenantMembership.user_id == current.id),
        )
        .join(ResellerCustomer, ResellerCustomer.reseller_id == ResellerAccount.id)
        .join(Tenant, Tenant.id == ResellerCustomer.customer_tenant_id)
        .where(
            ResellerAccount.status == "active",
            TenantMembership.status == MembershipStatus.active,
            TenantMembership.role == MembershipRole.tenant_admin,
        )
        .order_by(Tenant.name)
    ).all()
    permissions = sorted(RESELLER_DELEGATED_PERMISSIONS)
    for reseller, _customer, tenant in delegated_rows:
        if str(tenant.id) in known:
            continue
        items.append(
            _context(
                tenant,
                role="reseller_admin",
                access_kind="reseller_customer",
                reseller_tenant_id=str(reseller.tenant_id),
                permissions=permissions,
            )
        )
        known.add(str(tenant.id))

    items.sort(key=lambda item: (item["tenant_name"].casefold(), item["tenant_id"]))
    return {"items": items}
