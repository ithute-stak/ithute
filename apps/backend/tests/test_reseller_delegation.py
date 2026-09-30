import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.deps import require_tenant_permission
from app.core.security import hash_password
from app.models import (
    MembershipRole,
    ResellerAccount,
    ResellerCustomer,
    Tenant,
    TenantMembership,
    User,
)


def _make_reseller_graph(db):
    reseller_tenant = Tenant(name="Reseller Co", slug=f"reseller-{uuid.uuid4().hex[:10]}")
    customer_tenant = Tenant(name="Customer Co", slug=f"customer-{uuid.uuid4().hex[:10]}")
    outsider_tenant = Tenant(name="Outsider Co", slug=f"outsider-{uuid.uuid4().hex[:10]}")
    user = User(
        email=f"reseller-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password("Reseller-Delegation-Test!"),
        full_name="Reseller Admin",
        is_active=True,
    )
    db.add_all([reseller_tenant, customer_tenant, outsider_tenant, user])
    db.flush()
    membership = TenantMembership(tenant_id=reseller_tenant.id, user_id=user.id, role=MembershipRole.tenant_admin)
    reseller = ResellerAccount(tenant_id=reseller_tenant.id, status="active", max_customers=10)
    db.add_all([membership, reseller])
    db.flush()
    link = ResellerCustomer(reseller_id=reseller.id, customer_tenant_id=customer_tenant.id)
    db.add(link)
    db.commit()
    return user, reseller_tenant, customer_tenant, outsider_tenant, reseller


def _cleanup(db, user, reseller_tenant, customer_tenant, outsider_tenant, reseller):
    db.execute(delete(ResellerCustomer).where(ResellerCustomer.reseller_id == reseller.id))
    db.execute(delete(ResellerAccount).where(ResellerAccount.id == reseller.id))
    db.execute(delete(TenantMembership).where(TenantMembership.user_id == user.id))
    db.execute(delete(User).where(User.id == user.id))
    db.execute(delete(Tenant).where(Tenant.id.in_([reseller_tenant.id, customer_tenant.id, outsider_tenant.id])))
    db.commit()


@pytest.mark.parametrize("permission", ["hosting.read", "hosting.manage", "mail.read", "mail.manage", "dns.read", "dns.manage", "billing.read"])
def test_reseller_admin_can_operate_linked_customer_services(db, permission: str):
    graph = _make_reseller_graph(db)
    user, _reseller_tenant, customer_tenant, *_rest = graph
    try:
        assert require_tenant_permission(customer_tenant.id, permission, db, user) is None
    finally:
        _cleanup(db, *graph)


@pytest.mark.parametrize("permission", ["identity.manage", "api_keys.manage", "audit.read", "billing.manage"])
def test_reseller_delegation_does_not_grant_sensitive_customer_admin(db, permission: str):
    graph = _make_reseller_graph(db)
    user, _reseller_tenant, customer_tenant, *_rest = graph
    try:
        with pytest.raises(HTTPException) as exc:
            require_tenant_permission(customer_tenant.id, permission, db, user)
        assert exc.value.status_code == 403
    finally:
        _cleanup(db, *graph)


def test_reseller_cannot_manage_unlinked_tenant(db):
    graph = _make_reseller_graph(db)
    user, _reseller_tenant, _customer_tenant, outsider_tenant, _reseller = graph
    try:
        with pytest.raises(HTTPException) as exc:
            require_tenant_permission(outsider_tenant.id, "hosting.manage", db, user)
        assert exc.value.status_code == 403
    finally:
        _cleanup(db, *graph)
