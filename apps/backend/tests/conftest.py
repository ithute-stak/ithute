import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    ApiKey,
    AuditLog,
    Invitation,
    MembershipRole,
    Tenant,
    TenantMembership,
    User,
    UserSession,
)

PASSWORD = "Phase1-Test-Password!"


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def deterministic_domain_create_dns(monkeypatch):
    """Avoid public DNS calls from unrelated API tests.

    Historical domain tests expect the TXT migration path. Individual tests for
    the new registrar-domain path can override these two API-level probes.
    """
    monkeypatch.setattr(
        "app.api.v1.domains.inspect_nameservers",
        lambda name, platform: {
            "lookup_status": "found",
            "lookup_detail": None,
            "current_nameservers": ["ns1.external.test", "ns2.external.test"],
            "current_provider": "External DNS provider",
            "platform_nameservers": ["ns1.ithute.co.ls", "ns2.ithute.co.ls"],
            "platform_nameservers_configured": True,
            "already_on_platform_nameservers": False,
        },
    )
    monkeypatch.setattr(
        "app.api.v1.domains.inspect_existing_records",
        lambda name: {
            "has_existing_dns_records": True,
            "existing_record_types": ["A"],
            "record_lookup_status": "found",
            "record_lookup_errors": [],
        },
    )


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


@pytest.fixture()
def platform_owner(db):
    user = User(
        email=f"owner-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="Phase 2 Owner",
        is_platform_owner=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.execute(delete(AuditLog).where(AuditLog.actor_user_id == user.id))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(delete(ApiKey).where(ApiKey.owner_user_id == user.id))
    db.execute(delete(User).where(User.id == user.id))
    db.commit()


@pytest.fixture()
def tenant_admin(db):
    tenant = Tenant(name="Admin Test Tenant", slug=f"admin-{uuid.uuid4().hex[:12]}")
    user = User(
        email=f"admin-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="Tenant Admin",
        is_active=True,
    )
    db.add_all([tenant, user])
    db.flush()
    membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role=MembershipRole.tenant_admin)
    db.add(membership)
    db.commit()
    db.refresh(user)
    db.refresh(tenant)
    yield user, tenant, membership
    db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant.id))
    db.execute(delete(Invitation).where(Invitation.tenant_id == tenant.id))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(delete(TenantMembership).where(TenantMembership.tenant_id == tenant.id))
    db.execute(delete(User).where(User.id == user.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()


@pytest.fixture()
def tenant_member(db):
    tenant = Tenant(name="Isolation Test Tenant", slug=f"isolation-{uuid.uuid4().hex[:12]}")
    user = User(
        email=f"member-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(PASSWORD),
        full_name="Tenant Member",
        is_active=True,
    )
    db.add_all([tenant, user])
    db.flush()
    membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role=MembershipRole.member)
    db.add(membership)
    db.commit()
    db.refresh(user)
    yield user
    db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant.id))
    db.execute(delete(Invitation).where(Invitation.tenant_id == tenant.id))
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.execute(delete(TenantMembership).where(TenantMembership.tenant_id == tenant.id))
    db.execute(delete(User).where(User.id == user.id))
    db.execute(delete(Tenant).where(Tenant.id == tenant.id))
    db.commit()