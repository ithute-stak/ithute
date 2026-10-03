import uuid

from sqlalchemy import delete, select

from app.models import AuditLog, MailNode, MailNodeAgent, MailNodeCommand
from app.models.domains import Domain, DomainDnsMode, DomainStatus
from app.models.mail import DistributionGroup, DistributionGroupMember, MailAlias, Mailbox
from app.services.mailboxes import hash_mailbox_password, mailbox_address, normalize_local_part

PASSWORD = "Phase1-Test-Password!"


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_domain(db, user, tenant):
    name = f"mail-{uuid.uuid4().hex[:10]}.example.com"
    domain = Domain(
        tenant_id=tenant.id,
        ascii_name=name,
        unicode_name=name,
        status=DomainStatus.verified,
        dns_mode=DomainDnsMode.external,
        mail_enabled=True,
        verification_token_hash="0" * 64,
        verification_token_hint="fixture",
        verification_record_name=f"_mailbox-dns-verification.{name}",
        created_by_user_id=user.id,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


def cleanup(db, domain):
    group_ids = list(db.scalars(select(DistributionGroup.id).where(DistributionGroup.domain_id == domain.id)))
    if group_ids:
        db.execute(delete(DistributionGroupMember).where(DistributionGroupMember.group_id.in_(group_ids)))
    db.execute(delete(MailAlias).where(MailAlias.domain_id == domain.id))
    db.execute(delete(DistributionGroup).where(DistributionGroup.domain_id == domain.id))
    mailbox_ids = [str(x) for x in db.scalars(select(Mailbox.id).where(Mailbox.domain_id == domain.id))]
    db.execute(delete(Mailbox).where(Mailbox.domain_id == domain.id))
    for resource_id in mailbox_ids:
        db.execute(delete(AuditLog).where(AuditLog.resource_id == resource_id))
    db.execute(delete(Domain).where(Domain.id == domain.id))
    db.commit()


def test_mailbox_helpers():
    assert normalize_local_part(" Sales.Team ") == "sales.team"
    assert mailbox_address("Sales", "Example.COM") == "sales@example.com"
    assert hash_mailbox_password("StrongMailbox1!").startswith("{SHA512-CRYPT}$6$")


def test_mailbox_lifecycle_alias_and_group(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    domain = make_domain(db, user, tenant)

    created = client.post(
        f"/api/v1/tenants/{tenant.id}/mailboxes",
        headers=headers,
        json={
            "domain_id": str(domain.id),
            "local_part": "alice",
            "password": "StrongMailbox1!",
            "quota_bytes": 1073741824,
        },
    )
    assert created.status_code == 201, created.text
    mailbox = created.json()
    assert mailbox["address"] == f"alice@{domain.ascii_name}"
    assert mailbox["status"] == "active"
    assert mailbox["storage_type"] == "internal"
    assert mailbox["mail_node_id"] is None

    suspended = client.post(f"/api/v1/tenants/{tenant.id}/mailboxes/{mailbox['id']}/suspend", headers=headers)
    assert suspended.status_code == 200 and suspended.json()["status"] == "suspended"
    restored = client.post(f"/api/v1/tenants/{tenant.id}/mailboxes/{mailbox['id']}/restore", headers=headers)
    assert restored.status_code == 200 and restored.json()["status"] == "active"
    changed = client.post(
        f"/api/v1/tenants/{tenant.id}/mailboxes/{mailbox['id']}/password",
        headers=headers,
        json={"password": "AnotherStrong2!"},
    )
    assert changed.status_code == 200

    alias = client.post(
        f"/api/v1/tenants/{tenant.id}/aliases",
        headers=headers,
        json={"domain_id": str(domain.id), "local_part": "support", "destination_address": mailbox["address"]},
    )
    assert alias.status_code == 201, alias.text

    group = client.post(
        f"/api/v1/tenants/{tenant.id}/groups",
        headers=headers,
        json={"domain_id": str(domain.id), "local_part": "team", "display_name": "Team"},
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]
    member = client.post(
        f"/api/v1/tenants/{tenant.id}/groups/{group_id}/members",
        headers=headers,
        json={"destination_address": mailbox["address"]},
    )
    assert member.status_code == 201, member.text

    listed = client.get(f"/api/v1/tenants/{tenant.id}/mailboxes", headers=headers)
    assert listed.status_code == 200 and listed.json()["total"] >= 1

    removed_member = client.delete(
        f"/api/v1/tenants/{tenant.id}/groups/{group_id}/members/{member.json()['id']}",
        headers=headers,
    )
    assert removed_member.status_code == 204
    deleted_group = client.delete(f"/api/v1/tenants/{tenant.id}/groups/{group_id}", headers=headers)
    assert deleted_group.status_code == 204
    deleted_alias = client.delete(f"/api/v1/tenants/{tenant.id}/aliases/{alias.json()['id']}", headers=headers)
    assert deleted_alias.status_code == 204

    archived = client.delete(f"/api/v1/tenants/{tenant.id}/mailboxes/{mailbox['id']}", headers=headers)
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    cleanup(db, domain)


def test_external_mailbox_requires_registered_node(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    headers = login(client, user.email)
    domain = make_domain(db, user, tenant)

    response = client.post(
        f"/api/v1/tenants/{tenant.id}/mailboxes",
        headers=headers,
        json={
            "domain_id": str(domain.id),
            "local_part": "external",
            "password": "StrongMailbox1!",
            "quota_bytes": 1073741824,
            "storage_type": "external",
        },
    )
    assert response.status_code == 422
    assert "mail node" in response.json()["detail"].lower()
    cleanup(db, domain)


def test_external_mailbox_queues_secure_node_command(client, db, tenant_admin, platform_owner):
    platform_headers = login(client, platform_owner.email)
    node_name = f"mail-node-{uuid.uuid4().hex[:8]}"
    created_node = client.post(
        "/api/v1/platform/mail-nodes",
        headers=platform_headers,
        json={
            "name": node_name,
            "role": "combined",
            "region": "lesotho",
            "hostname": f"{node_name}.example.com",
            "ssh_port": 22,
            "storage_path": "/srv/ithute-mail",
            "capabilities": ["mail", "storage"],
        },
    )
    assert created_node.status_code == 201, created_node.text
    node_id = created_node.json()["id"]

    credential = client.post(
        f"/api/v1/platform/mail-nodes/{node_id}/agent-token",
        headers=platform_headers,
    )
    assert credential.status_code == 200, credential.text
    agent_token = credential.json()["token"]

    user, tenant, _ = tenant_admin
    tenant_headers = login(client, user.email)
    domain = make_domain(db, user, tenant)
    created = client.post(
        f"/api/v1/tenants/{tenant.id}/mailboxes",
        headers=tenant_headers,
        json={
            "domain_id": str(domain.id),
            "local_part": "remote",
            "password": "StrongMailbox1!",
            "quota_bytes": 1073741824,
            "storage_type": "external",
            "mail_node_id": node_id,
        },
    )
    assert created.status_code == 201, created.text
    mailbox = created.json()
    assert mailbox["storage_type"] == "external"
    assert mailbox["mail_node_id"] == node_id

    queued = db.scalar(
        select(MailNodeCommand).where(
            MailNodeCommand.mailbox_id == uuid.UUID(mailbox["id"]),
            MailNodeCommand.status == "queued",
        )
    )
    assert queued is not None

    claimed = client.post(
        "/api/v1/mail-node-agent/commands/claim",
        headers={"X-Ithute-Mail-Agent": agent_token},
        json={},
    )
    assert claimed.status_code == 200, claimed.text
    command = claimed.json()["command"]
    assert command["payload"]["address"] == mailbox["address"]
    assert command["payload"]["status"] == "active"

    completed = client.post(
        f"/api/v1/mail-node-agent/commands/{command['id']}/status",
        headers={"X-Ithute-Mail-Agent": agent_token},
        json={"status": "completed"},
    )
    assert completed.status_code == 200, completed.text

    cleanup(db, domain)
    db.execute(delete(MailNodeCommand).where(MailNodeCommand.node_id == uuid.UUID(node_id)))
    db.execute(delete(MailNodeAgent).where(MailNodeAgent.node_id == uuid.UUID(node_id)))
    db.execute(delete(MailNode).where(MailNode.id == uuid.UUID(node_id)))
    db.commit()


def test_member_without_mail_permission_is_forbidden(client, tenant_member):
    membership = tenant_member.memberships[0]
    headers = login(client, tenant_member.email)
    response = client.get(f"/api/v1/tenants/{membership.tenant_id}/mailboxes", headers=headers)
    assert response.status_code == 403
