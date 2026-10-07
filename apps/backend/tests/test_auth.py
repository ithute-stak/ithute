from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.api.deps import get_current_user

from app.core.config import settings
from app.core.security import create_access_token, hash_token
from app.models import PasswordResetToken, User, UserSession

PASSWORD = "Phase1-Test-Password!"
NEW_PASSWORD = "Phase1-New-Secure-Password!"


def test_login_success_sets_secure_session_cookies(client, platform_owner):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": platform_owner.email, "password": PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["is_platform_owner"] is True
    assert "mdns_access" in response.cookies
    assert "mdns_refresh" in response.cookies


def test_cookie_auth_can_read_current_user(client, platform_owner):
    assert client.post("/api/v1/auth/login", json={"email": platform_owner.email, "password": PASSWORD}).status_code == 200
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == platform_owner.email


def test_refresh_rotates_session(client, db, platform_owner):
    assert client.post("/api/v1/auth/login", json={"email": platform_owner.email, "password": PASSWORD}).status_code == 200
    before = db.scalars(select(UserSession).where(UserSession.user_id == platform_owner.id)).all()
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    db.expire_all()
    after = db.scalars(select(UserSession).where(UserSession.user_id == platform_owner.id)).all()
    assert len(after) == len(before) + 1
    assert any(row.revoked_at is not None for row in after)


def test_login_rejects_wrong_password(client, platform_owner):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": platform_owner.email, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_rejects_inactive_user_without_revealing_account_state(client, db, platform_owner):
    user = db.scalar(select(User).where(User.id == platform_owner.id))
    user.is_active = False
    db.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": platform_owner.email, "password": PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_password_reset_request_does_not_enumerate_unknown_accounts(client):
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "missing-account@example.com"},
    )
    assert response.status_code == 202
    assert response.json() == {"accepted": True}


def test_password_reset_is_one_time_and_revokes_existing_sessions(client, db, platform_owner):
    assert client.post(
        "/api/v1/auth/login",
        json={"email": platform_owner.email, "password": PASSWORD},
    ).status_code == 200

    request = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": platform_owner.email},
    )
    assert request.status_code == 202
    token = request.json()["reset_token"]

    reset = client.post(
        "/api/v1/auth/password-reset/complete",
        json={"token": token, "new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 200
    assert reset.json() == {"reset": True}

    db.expire_all()
    sessions = db.scalars(select(UserSession).where(UserSession.user_id == platform_owner.id)).all()
    assert sessions
    assert all(row.revoked_at is not None for row in sessions)

    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": platform_owner.email, "password": PASSWORD},
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": platform_owner.email, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200

    replay = client.post(
        "/api/v1/auth/password-reset/complete",
        json={"token": token, "new_password": "Another-New-Secure-Password!"},
    )
    assert replay.status_code == 400
    assert "invalid or expired" in replay.json()["detail"].lower()


def test_expired_password_reset_token_is_rejected(client, db, platform_owner):
    raw = "expired-password-reset-token-that-is-long-enough"
    row = PasswordResetToken(
        user_id=platform_owner.id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db.add(row)
    db.commit()

    response = client.post(
        "/api/v1/auth/password-reset/complete",
        json={"token": raw, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert "invalid or expired" in response.json()["detail"].lower()


def test_protected_endpoint_rejects_missing_token(client):
    fresh = type(client)(client.app)
    response = fresh.get("/api/v1/tenants")
    assert response.status_code == 401


def test_auth_capabilities_keep_password_login_enabled_by_default_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "local_auth_enabled", True)

    response = client.get("/api/v1/auth/capabilities")

    assert response.status_code == 200
    assert response.json()["local_auth_enabled"] is True
    assert response.json()["local_security_controls_enabled"] is True


def test_production_central_session_can_read_me_when_local_auth_is_disabled(client, platform_owner, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "legacy_local_auth_production_enabled", False)
    client.app.dependency_overrides[get_current_user] = lambda: platform_owner
    try:
        response = client.get("/api/v1/auth/me")
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json()["email"] == platform_owner.email


def test_central_auth_enforcement_blocks_password_login_across_devices(client, db, platform_owner, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "local_auth_enabled", True)

    user = db.get(User, platform_owner.id)
    user.central_auth_enforced = True
    user.central_auth_enforced_at = datetime.now(timezone.utc)
    db.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": platform_owner.email, "password": PASSWORD},
    )

    assert login.status_code == 403
    assert login.json()["detail"]["code"] == "CENTRAL_AUTH_REQUIRED"
    assert login.json()["detail"]["message"] == "This account requires Ithute Central Authentication."


def test_existing_local_session_is_rejected_after_central_auth_is_enforced(client, db, platform_owner):
    user = db.get(User, platform_owner.id)
    token = create_access_token(str(user.id), {"sv": user.session_version})

    user.central_auth_enforced = True
    user.central_auth_enforced_at = datetime.now(timezone.utc)
    db.commit()

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "CENTRAL_AUTH_REQUIRED"


def test_password_reset_sends_one_time_verification_email(client, platform_owner, monkeypatch):
    from app.api.v1 import auth as auth_api

    sent = {}
    def capture(to_address, subject, text_body, html_body=None):
        sent.update(
            to_address=to_address,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    monkeypatch.setattr(auth_api, "send_system_email", capture)

    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": platform_owner.email},
    )

    assert response.status_code == 202
    assert sent["to_address"] == platform_owner.email
    assert sent["subject"] == "Reset your Ithute password"
    assert "one-time verification link" in sent["text_body"]
    assert "Verify and reset password" in sent["html_body"]
    assert "#token=" in sent["html_body"]


def test_central_auth_hardened_account_cannot_issue_local_reset_token(client, db, platform_owner, monkeypatch):
    from app.api.v1 import auth as auth_api

    user = db.get(User, platform_owner.id)
    user.central_auth_enforced = True
    user.central_auth_enforced_at = datetime.now(timezone.utc)
    db.commit()

    sent = {}
    monkeypatch.setattr(
        auth_api,
        "send_system_email",
        lambda to_address, subject, text_body, html_body=None: sent.update(
            to_address=to_address, subject=subject, text_body=text_body, html_body=html_body
        ),
    )

    before = db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)).all()
    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": user.email},
    )
    db.expire_all()
    after = db.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)).all()

    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert len(after) == len(before)
    assert sent["subject"] == "Ithute account recovery notice"
    assert "Central Authentication" in sent["text_body"]


def test_central_auth_hardened_account_rejects_preexisting_reset_token(client, db, platform_owner):
    raw = "preexisting-reset-token-that-is-long-enough"
    token = PasswordResetToken(
        user_id=platform_owner.id,
        token_hash=hash_token(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    user = db.get(User, platform_owner.id)
    user.central_auth_enforced = True
    user.central_auth_enforced_at = datetime.now(timezone.utc)
    db.add(token)
    db.commit()

    response = client.post(
        "/api/v1/auth/password-reset/complete",
        json={"token": raw, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 400
    assert "invalid or expired" in response.json()["detail"].lower()
    db.refresh(token)
    assert token.used_at is not None
