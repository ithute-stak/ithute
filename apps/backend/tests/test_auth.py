from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import hash_token
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
