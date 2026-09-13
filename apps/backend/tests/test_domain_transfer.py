import uuid

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.models import (
    AuditLog,
    DkimKey,
    DistributionGroup,
    MailAlias,
    Mailbox,
    MailboxPolicy,
    MembershipRole,
    Tenant,
    TenantMembership,
)
from app.models.domains import Domain, DomainEvent

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def cleanup_transfer(db, domain_id, *tenant_ids):
    db.execute(delete(AuditLog).where(AuditLog.resource_id == str(domain_id)))
    db.execute(delete(DomainEvent).where(DomainEvent.domain_id == domain_id))
    db.execute(delete(Domain).where(Domain.id == domain_id))
    for tenant_id in tenant_ids:
        db.execute(delete(TenantMembership).where(TenantMembership.tenant_id == tenant_id))
        db.execute(delete(AuditLog).where(AuditLog.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
    db.commit()


def test_platform_owner_transfers_domain_with_mail_resources(client, db, platform_owner):
    source = Tenant(name="Transfer Source", slug=f"transfer-source-{uuid.uuid4().hex[:10]}")
    target = Tenant(name="Transfer Target", slug=f"transfer-target-{uuid.uuid4().hex[:10]}")
    db.add_all([source, target])
    db.commit()
    db.refresh(source)
    db.refresh(target)

    headers = login(client, platform_owner.email)
    name = f"transfer-{uuid.uuid4().hex[:10]}.example.com"
    created = client.post(
        f"/api/v1/tenants/{source.id}/domains",
        headers=headers,
        json={"name": name, "dns_mode": "external"},
    )
    assert created.status_code == 201, created.text
    domain_id = uuid.UUID(created.json()["id"])

    mailbox = Mailbox(
        tenant_id=source.id,
        domain_id=domain_id,
        local_part="hello",
        address=f"hello@{name}",
        password_hash=hash_password("Mailbox-Transfer-Test!"),
        created_by_user_id=platform_owner.id,
    )
    alias = MailAlias(
        tenant_id=source.id,
        domain_id=domain_id,
        source_address=f"info@{name}",
        destination_address=f"hello@{name}",
        created_by_user_id=platform_owner.id,
    )
    group = DistributionGroup(
        tenant_id=source.id,
        domain_id=domain_id,
        local_part="team",
        address=f"team@{name}",
        created_by_user_id=platform_owner.id,
    )
    dkim = DkimKey(
        tenant_id=source.id,
        domain_id=domain_id,
        selector="default",
        public_key_b64="test-public",
        private_key_encrypted="test-private",
        created_by_user_id=platform_owner.id,
    )
    db.add_all([mailbox, alias, group, dkim])
    db.flush()
    policy = MailboxPolicy(
        tenant_id=source.id,
        mailbox_id=mailbox.id,
        updated_by_user_id=platform_owner.id,
    )
    db.add(policy)
    db.commit()

    transferred = client.post(
        f"/api/v1/tenants/{source.id}/domains/{domain_id}/transfer",
        headers=headers,
        json={"target_tenant_id": str(target.id)},
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["tenant_id"] == str(target.id)
    assert transferred.json()["id"] == str(domain_id)
    assert transferred.json()["ascii_name"] == name

    db.expire_all()
    assert db.get(Domain, domain_id).tenant_id == target.id
    assert db.scalar(select(Mailbox).where(Mailbox.id == mailbox.id)).tenant_id == target.id
    assert db.scalar(select(MailAlias).where(MailAlias.id == alias.id)).tenant_id == target.id
    assert db.scalar(select(DistributionGroup).where(DistributionGroup.id == group.id)).tenant_id == target.id
    assert db.scalar(select(DkimKey).where(DkimKey.id == dkim.id)).tenant_id == target.id
    assert db.scalar(select(MailboxPolicy).where(MailboxPolicy.id == policy.id)).tenant_id == target.id

    old_lookup = client.get(f"/api/v1/tenants/{source.id}/domains/{domain_id}", headers=headers)
    new_lookup = client.get(f"/api/v1/tenants/{target.id}/domains/{domain_id}", headers=headers)
    assert old_lookup.status_code == 404
    assert new_lookup.status_code == 200

    events = db.scalars(select(DomainEvent).where(DomainEvent.domain_id == domain_id)).all()
    transfer_out = next(event for event in events if event.event_type == "domain.transfer_out")
    transfer_in = next(event for event in events if event.event_type == "domain.transfer_in")
    assert transfer_out.tenant_id == source.id
    assert transfer_in.tenant_id == target.id

    source_audit = db.scalar(
        select(AuditLog).where(
            AuditLog.resource_id == str(domain_id),
            AuditLog.tenant_id == source.id,
            AuditLog.action == "domain.transfer_out",
        )
    )
    target_audit = db.scalar(
        select(AuditLog).where(
            AuditLog.resource_id == str(domain_id),
            AuditLog.tenant_id == target.id,
            AuditLog.action == "domain.transfer_in",
        )
    )
    assert source_audit is not None
    assert target_audit is not None

    cleanup_transfer(db, domain_id, source.id, target.id)


def test_tenant_admin_requires_admin_access_to_destination(client, db, tenant_admin):
    user, source, _ = tenant_admin
    target = Tenant(name="Unauthorized Transfer Target", slug=f"transfer-no-access-{uuid.uuid4().hex[:10]}")
    db.add(target)
    db.commit()
    db.refresh(target)

    headers = login(client, user.email)
    created = client.post(
        f"/api/v1/tenants/{source.id}/domains",
        headers=headers,
        json={"name": f"blocked-transfer-{uuid.uuid4().hex[:10]}.example.com", "dns_mode": "external"},
    )
    assert created.status_code == 201, created.text
    domain_id = uuid.UUID(created.json()["id"])

    blocked = client.post(
        f"/api/v1/tenants/{source.id}/domains/{domain_id}/transfer",
        headers=headers,
        json={"target_tenant_id": str(target.id)},
    )
    assert blocked.status_code == 403
    assert db.get(Domain, domain_id).tenant_id == source.id

    membership = TenantMembership(
        tenant_id=target.id,
        user_id=user.id,
        role=MembershipRole.tenant_admin,
    )
    db.add(membership)
    db.commit()

    allowed = client.post(
        f"/api/v1/tenants/{source.id}/domains/{domain_id}/transfer",
        headers=headers,
        json={"target_tenant_id": str(target.id)},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["tenant_id"] == str(target.id)

    cleanup_transfer(db, domain_id, target.id)
