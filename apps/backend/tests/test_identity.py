from uuid import UUID

import pyotp
from sqlalchemy import select

from app.models import ApiKey, MembershipRole, TenantMembership, User

PASSWORD = "Phase1-Test-Password!"


def login(client, email, password=PASSWORD, mfa_code=None):
    payload = {"email": email, "password": password}
    if mfa_code:
        payload["mfa_code"] = mfa_code
    return client.post("/api/v1/auth/login", json=payload)


def test_global_identity_has_membership_not_tenant_on_user(db, tenant_admin):
    user, tenant, membership = tenant_admin
    stored = db.get(User, user.id)
    assert stored.email == user.email
    assert membership.tenant_id == tenant.id
    assert membership.user_id == user.id
    assert membership.role == MembershipRole.tenant_admin
    assert not hasattr(stored, "tenant_id")


def test_tenant_admin_can_invite_and_accept_member(client, db, tenant_admin):
    admin, tenant, _ = tenant_admin
    assert login(client, admin.email).status_code == 200
    invited = client.post(
        f"/api/v1/tenants/{tenant.id}/invitations",
        json={"email": "new-member@example.com", "role": "member"},
    )
    assert invited.status_code == 201
    token = invited.json()["token"]
    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"token": token, "full_name": "New Member", "password": "A-Strong-New-Password!"},
    )
    assert accepted.status_code == 200
    user_id = UUID(accepted.json()["user_id"])
    membership_id = UUID(accepted.json()["id"])
    assert db.scalar(select(TenantMembership).where(TenantMembership.id == membership_id)) is not None
    db.query(TenantMembership).filter(TenantMembership.id == membership_id).delete()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()


def test_member_cannot_invite(client, tenant_member):
    user = tenant_member
    assert login(client, user.email).status_code == 200
    membership = user.memberships[0]
    response = client.post(
        f"/api/v1/tenants/{membership.tenant_id}/invitations",
        json={"email": "forbidden@example.com", "role": "member"},
    )
    assert response.status_code == 403


def test_mfa_setup_enable_and_login_challenge(client, platform_owner):
    assert login(client, platform_owner.email).status_code == 200
    setup = client.post("/api/v1/auth/mfa/setup")
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    code = pyotp.TOTP(secret).now()
    enabled = client.post("/api/v1/auth/mfa/enable", json={"code": code})
    assert enabled.status_code == 204

    fresh_client = type(client)(client.app)
    challenged = login(fresh_client, platform_owner.email)
    assert challenged.status_code == 401
    assert challenged.json()["detail"] == "MFA code required"
    success = login(fresh_client, platform_owner.email, mfa_code=pyotp.TOTP(secret).now())
    assert success.status_code == 200


def test_password_change_revokes_existing_session(client, platform_owner):
    assert login(client, platform_owner.email).status_code == 200
    changed = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "Phase2-New-Password!"},
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client, platform_owner.email, password="Phase2-New-Password!").status_code == 200


def test_api_key_is_tenant_scoped_and_only_returned_once(client, db, tenant_admin):
    user, tenant, _ = tenant_admin
    assert login(client, user.email).status_code == 200
    created = client.post(
        "/api/v1/api-keys",
        json={"tenant_id": str(tenant.id), "name": "automation", "scopes": ["dns.read"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["key"].startswith("mdns_")
    assert created.json()["tenant_id"] == str(tenant.id)
    key_id = UUID(created.json()["id"])
    listed = client.get(f"/api/v1/api-keys?tenant_id={tenant.id}")
    assert listed.status_code == 200
    row = next(row for row in listed.json() if row["id"] == str(key_id))
    assert row["key"] is None
    assert row["tenant_id"] == str(tenant.id)
    assert client.delete(f"/api/v1/api-keys/{key_id}").status_code == 204
    db.expire_all()
    assert db.get(ApiKey, key_id).revoked_at is not None
