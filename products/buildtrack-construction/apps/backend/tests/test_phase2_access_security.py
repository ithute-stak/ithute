from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db.base import Base
from app.db.session import get_db
from app.main import app

ADMIN_PASSWORD = "Nthane!Secure2026X"


@pytest.fixture()
def clients(tmp_path: Path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    admin = TestClient(app)
    secondary = TestClient(app)
    try:
        yield admin, secondary
    finally:
        admin.close()
        secondary.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def phase1(client: TestClient) -> None:
    response = client.post(
        "/api/v1/foundation/bootstrap",
        json={"name": "Nthane Brothers", "code": "NTHANE", "head_office_name": "Head Office", "head_office_code": "HO", "head_office_district": "Maseru"},
    )
    assert response.status_code == 201, response.text


def admin_bootstrap(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/access/bootstrap-admin",
        json={"username": "admin", "email": "admin@nthane.example", "full_name": "System Administrator", "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_first_admin_bootstrap_closes_anonymous_phase1_access(clients) -> None:
    admin, anonymous = clients
    status = admin.get("/api/v1/access/setup-status").json()
    assert status["company_bootstrapped"] is False
    assert status["admin_bootstrapped"] is False

    phase1(admin)
    blocked = anonymous.get("/api/v1/foundation/summary")
    assert blocked.status_code == 401

    created = admin_bootstrap(admin)
    assert created["user"]["username"] == "admin"
    assert created["user"]["assignments"][0]["role_code"] == "SYSTEM_ADMIN"

    me = admin.get("/api/v1/access/me")
    assert me.status_code == 200
    assert "users.manage" in me.json()["permissions"]
    assert "security.manage" in me.json()["permissions"]

    summary = admin.get("/api/v1/foundation/summary")
    assert summary.status_code == 200

    no_cookie = anonymous.get("/api/v1/foundation/summary")
    assert no_cookie.status_code == 401


def test_scoped_branch_assignment_is_enforced_and_context_is_filtered(clients) -> None:
    admin, branch_user = clients
    phase1(admin)
    admin_bootstrap(admin)
    branch = admin.post("/api/v1/foundation/branches", json={"code": "BB", "name": "Butha-Buthe Branch", "district": "Butha-Buthe"}).json()
    site = admin.post("/api/v1/foundation/sites", json={"branch_id": branch["id"], "code": "BB-01", "name": "Butha-Buthe Yard", "site_type": "yard"}).json()
    catalog = admin.get("/api/v1/access/assignment-catalog").json()
    branch_role = next(role for role in catalog["roles"] if role["code"] == "BRANCH_MANAGER")

    created = admin.post(
        "/api/v1/access/users",
        json={
            "username": "bbmanager",
            "email": "bbmanager@nthane.example",
            "full_name": "Butha-Buthe Manager",
            "job_title": "Branch Manager",
            "temporary_password": "Branch!Secure2026X",
            "must_change_password": False,
            "assignments": [{"role_id": branch_role["id"], "branch_id": branch["id"], "site_id": None, "is_primary": True}],
        },
    )
    assert created.status_code == 201, created.text

    login = branch_user.post("/api/v1/access/login", json={"username": "bbmanager", "password": "Branch!Secure2026X"})
    assert login.status_code == 200
    context = branch_user.get("/api/v1/access/context")
    assert context.status_code == 200
    payload = context.json()
    assert payload["company_wide"] is False
    assert [row["id"] for row in payload["branches"]] == [branch["id"]]
    assert payload["sites"] == []
    assert "branches.view" in payload["permissions"]

    # Phase 1 administration is intentionally HQ/company scoped even when the
    # underlying role has a branch-scoped manage permission.
    assert branch_user.get("/api/v1/foundation/branches").status_code == 403
    assert branch_user.get("/api/v1/access/users").status_code == 403

    # Site roles carry exact site scope and inherit the site's branch.
    site_role = next(role for role in catalog["roles"] if role["code"] == "SITE_MANAGER")
    site_user = admin.post(
        "/api/v1/access/users",
        json={"username": "sitemanager", "email": "site@nthane.example", "full_name": "Site Manager", "temporary_password": "Site!Secure2026X", "assignments": [{"role_id": site_role["id"], "site_id": site["id"], "is_primary": True}]},
    )
    assert site_user.status_code == 201, site_user.text
    assignment = site_user.json()["user"]["assignments"][0]
    assert assignment["site_id"] == site["id"]
    assert assignment["branch_id"] == branch["id"]


def test_lockout_unlock_temporary_password_and_security_events(clients) -> None:
    admin, user_client = clients
    phase1(admin)
    admin_bootstrap(admin)
    catalog = admin.get("/api/v1/access/assignment-catalog").json()
    auditor = next(role for role in catalog["roles"] if role["code"] == "AUDITOR")
    created = admin.post(
        "/api/v1/access/users",
        json={"username": "auditor", "email": "auditor@nthane.example", "full_name": "Internal Auditor", "assignments": [{"role_id": auditor["id"], "is_primary": True}]},
    )
    assert created.status_code == 201
    temporary = created.json()["temporary_password"]
    assert temporary and len(temporary) >= 12
    user_id = created.json()["user"]["id"]

    for attempt in range(1, 6):
        response = user_client.post("/api/v1/access/login", json={"username": "auditor", "password": "Wrong!Password2026"})
        assert response.status_code in {401, 423}
        if attempt == 5:
            assert response.status_code == 423

    locked_correct = user_client.post("/api/v1/access/login", json={"username": "auditor", "password": temporary})
    assert locked_correct.status_code == 423

    unlock = admin.post(f"/api/v1/access/users/{user_id}/unlock")
    assert unlock.status_code == 200
    successful = user_client.post("/api/v1/access/login", json={"username": "auditor", "password": temporary})
    assert successful.status_code == 200
    assert successful.json()["must_change_password"] is True

    events = admin.get("/api/v1/access/security-events?limit=100")
    assert events.status_code == 200
    types = {event["event_type"] for event in events.json()}
    assert "login_failed" in types
    assert "account_unlocked" in types
    assert "login_success" in types


def test_password_change_reset_tokens_sessions_and_policy(clients) -> None:
    admin, user_client = clients
    phase1(admin)
    admin_bootstrap(admin)
    catalog = admin.get("/api/v1/access/assignment-catalog").json()
    auditor = next(role for role in catalog["roles"] if role["code"] == "AUDITOR")
    created = admin.post(
        "/api/v1/access/users",
        json={"username": "securityuser", "email": "securityuser@nthane.example", "full_name": "Security Test User", "temporary_password": "Initial!Secure2026X", "assignments": [{"role_id": auditor["id"], "is_primary": True}]},
    ).json()
    user_id = created["user"]["id"]

    assert user_client.post("/api/v1/access/login", json={"username": "securityuser", "password": "Initial!Secure2026X"}).status_code == 200
    change = user_client.post("/api/v1/access/change-password", json={"current_password": "Initial!Secure2026X", "new_password": "Changed!Secure2027Y"})
    assert change.status_code == 200, change.text
    reuse = user_client.post("/api/v1/access/change-password", json={"current_password": "Changed!Secure2027Y", "new_password": "Initial!Secure2026X"})
    assert reuse.status_code == 422

    reset = admin.post(f"/api/v1/access/users/{user_id}/reset-token")
    assert reset.status_code == 200
    token = reset.json()["reset_token"]
    consumed = user_client.post("/api/v1/access/reset-password", json={"token": token, "new_password": "Reset!Secure2028Z"})
    assert consumed.status_code == 200, consumed.text
    second_use = user_client.post("/api/v1/access/reset-password", json={"token": token, "new_password": "Other!Secure2029Z"})
    assert second_use.status_code == 422

    # Password reset revokes all previous sessions.
    assert user_client.get("/api/v1/access/me").status_code == 401
    assert user_client.post("/api/v1/access/login", json={"username": "securityuser", "password": "Reset!Secure2028Z"}).status_code == 200

    policy = admin.get("/api/v1/access/security-policy")
    assert policy.status_code == 200
    new_policy = dict(policy.json())
    new_policy["minimum_password_length"] = 14
    new_policy["idle_minutes"] = 30
    updated = admin.put("/api/v1/access/security-policy", json=new_policy)
    assert updated.status_code == 200
    assert updated.json()["policy"]["minimum_password_length"] == 14
    assert updated.json()["policy"]["idle_minutes"] == 30


def test_session_inventory_and_admin_revoke_all(clients) -> None:
    admin, user_client = clients
    phase1(admin)
    admin_bootstrap(admin)
    catalog = admin.get("/api/v1/access/assignment-catalog").json()
    auditor = next(role for role in catalog["roles"] if role["code"] == "AUDITOR")
    user = admin.post(
        "/api/v1/access/users",
        json={"username": "sessionuser", "email": "session@nthane.example", "full_name": "Session User", "temporary_password": "Session!Secure2026X", "assignments": [{"role_id": auditor["id"], "is_primary": True}]},
    ).json()["user"]
    assert user_client.post("/api/v1/access/login", json={"username": "sessionuser", "password": "Session!Secure2026X"}).status_code == 200
    own = user_client.get("/api/v1/access/sessions")
    assert own.status_code == 200
    assert any(item["current"] for item in own.json())

    inventory = admin.get(f"/api/v1/access/users/{user['id']}/sessions")
    assert inventory.status_code == 200
    assert inventory.json()
    revoked = admin.post(f"/api/v1/access/users/{user['id']}/sessions/revoke-all")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_sessions"] >= 1
    assert user_client.get("/api/v1/access/me").status_code == 401
