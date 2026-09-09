from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.api.v1 import document_downloads, foundation
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def client(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    foundation.settings.media_root = str(tmp_path / "media")
    document_downloads.settings.media_root = str(tmp_path / "media")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def bootstrap(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/foundation/bootstrap",
        json={
            "name": "Nthane Brothers",
            "legal_name": "Nthane Brothers",
            "code": "NTHANE",
            "head_office_name": "Head Office",
            "head_office_code": "HO",
            "head_office_district": "Maseru",
        },
    )
    assert response.status_code == 201, response.text
    admin = client.post(
        "/api/v1/access/bootstrap-admin",
        json={
            "username": "admin",
            "email": "admin@nthane.example.com",
            "full_name": "BuildTrack Administrator",
            "password": "BuildTrack!Root2026X",
        },
    )
    assert admin.status_code == 201, admin.text
    return response.json()


def test_phase1_bootstrap_creates_complete_control_plane(client: TestClient) -> None:
    bootstrap(client)

    summary = client.get("/api/v1/foundation/summary")
    assert summary.status_code == 200
    counts = summary.json()["counts"]
    assert counts["branches"] == 1
    assert counts["departments"] == 9
    assert counts["cost_centres"] == 1
    assert counts["roles"] == 7
    assert counts["permissions"] >= 46
    assert counts["approval_workflows"] == 1
    assert counts["number_sequences"] == 8
    assert counts["master_data_categories"] == 2

    company = summary.json()["company"]
    assert company["country"] == "Lesotho"
    assert company["currency"] == "LSL"
    assert company["currency_symbol"] == "M"
    assert company["timezone"] == "Africa/Maseru"

    second_bootstrap = client.post("/api/v1/foundation/bootstrap", json={})
    assert second_bootstrap.status_code == 409


def test_branch_site_department_cost_centre_hierarchy_is_enforced(client: TestClient) -> None:
    bootstrap(client)
    branch = client.post(
        "/api/v1/foundation/branches",
        json={"code": "BB", "name": "Butha-Buthe Branch", "district": "Butha-Buthe"},
    )
    assert branch.status_code == 201, branch.text
    branch_id = branch.json()["id"]

    site = client.post(
        "/api/v1/foundation/sites",
        json={"branch_id": branch_id, "code": "BB-01", "name": "Butha-Buthe Operations Yard", "site_type": "yard"},
    )
    assert site.status_code == 201, site.text
    site_id = site.json()["id"]

    department = client.post(
        "/api/v1/foundation/departments",
        json={"branch_id": branch_id, "code": "OPS", "name": "Branch Operations"},
    )
    assert department.status_code == 201

    cost_centre = client.post(
        "/api/v1/foundation/cost-centres",
        json={
            "branch_id": branch_id,
            "site_id": site_id,
            "department_id": department.json()["id"],
            "code": "BB-OPS",
            "name": "Butha-Buthe Operations",
            "cost_centre_type": "operational",
        },
    )
    assert cost_centre.status_code == 201, cost_centre.text

    other_branch = client.post("/api/v1/foundation/branches", json={"code": "LR", "name": "Leribe Branch"}).json()
    mismatch = client.post(
        "/api/v1/foundation/cost-centres",
        json={"branch_id": other_branch["id"], "site_id": site_id, "code": "BAD", "name": "Invalid Scope"},
    )
    assert mismatch.status_code == 422
    assert "Site does not belong" in mismatch.text


def test_roles_permissions_and_multistep_approval_engine(client: TestClient) -> None:
    bootstrap(client)
    roles = client.get("/api/v1/foundation/roles").json()
    permissions = client.get("/api/v1/foundation/permissions").json()
    assert all(role["permission_ids"] for role in roles if role["code"] != "SITE_MANAGER") or roles

    view_permissions = [permission["id"] for permission in permissions if permission["action"] == "view"]
    custom_role = client.post(
        "/api/v1/foundation/roles",
        json={"code": "QS", "name": "Quantity Surveyor", "scope_level": "branch", "permission_ids": view_permissions},
    )
    assert custom_role.status_code == 201
    assert len(custom_role.json()["permission_ids"]) == len(view_permissions)

    workflows = client.get("/api/v1/foundation/approval-workflows").json()
    procurement = next(item for item in workflows if item["code"] == "PROCUREMENT_STANDARD")
    assert len(procurement["steps"]) == 2

    branch = client.get("/api/v1/foundation/branches").json()[0]
    approval = client.post(
        "/api/v1/foundation/approval-requests",
        json={
            "workflow_id": procurement["id"],
            "branch_id": branch["id"],
            "entity_type": "purchase_requisition",
            "entity_id": "REQ-001",
            "title": "Plant spare parts",
            "amount": "7500.00",
            "requested_by": "Procurement Officer",
        },
    )
    assert approval.status_code == 201, approval.text
    request_id = approval.json()["id"]
    assert approval.json()["reference"].startswith("APR-")

    branch_manager = next(role for role in roles if role["code"] == "BRANCH_MANAGER")
    hq_executive = next(role for role in roles if role["code"] == "HQ_EXECUTIVE")

    step_one = client.post(
        f"/api/v1/foundation/approval-requests/{request_id}/actions",
        json={"role_id": branch_manager["id"], "actor_name": "Branch Manager", "action": "approve", "comment": "Checked"},
    )
    assert step_one.status_code == 200
    assert step_one.json()["status"] == "pending"
    assert step_one.json()["current_step_order"] == 2

    step_two = client.post(
        f"/api/v1/foundation/approval-requests/{request_id}/actions",
        json={"role_id": hq_executive["id"], "actor_name": "HQ Executive", "action": "approve", "comment": "Approved"},
    )
    assert step_two.status_code == 200
    assert step_two.json()["status"] == "approved"
    assert step_two.json()["completed_at"]


def test_numbering_document_versioning_download_and_audit(client: TestClient) -> None:
    bootstrap(client)
    sequences = client.get("/api/v1/foundation/number-sequences").json()
    tender_sequence = next(item for item in sequences if item["code"] == "TENDER")
    first = client.post(f"/api/v1/foundation/number-sequences/{tender_sequence['id']}/next").json()["reference"]
    second = client.post(f"/api/v1/foundation/number-sequences/{tender_sequence['id']}/next").json()["reference"]
    assert first != second
    assert first.startswith("TND-")

    document = client.post(
        "/api/v1/foundation/documents",
        json={"title": "Phase 1 Governance Manual", "category": "Corporate", "confidentiality": "internal", "created_by": "System Setup"},
    )
    assert document.status_code == 201, document.text
    document_id = document.json()["id"]
    assert document.json()["document_number"].startswith("DOC-")

    upload = client.post(
        f"/api/v1/foundation/documents/{document_id}/versions",
        files={"file": ("governance.txt", b"BuildTrack Phase 1 governance", "text/plain")},
        data={"uploaded_by": "System Setup", "note": "Initial controlled copy"},
    )
    assert upload.status_code == 201, upload.text
    version = upload.json()
    assert version["version_number"] == 1
    assert len(version["sha256"]) == 64

    download = client.get(f"/api/v1/foundation/documents/{document_id}/versions/{version['id']}/download")
    assert download.status_code == 200
    assert download.content == b"BuildTrack Phase 1 governance"

    audit = client.get("/api/v1/foundation/audit?limit=250")
    assert audit.status_code == 200
    actions = {entry["action"] for entry in audit.json()}
    assert "phase1.bootstrap" in actions
    assert "number_sequence.issue" in actions
    assert "document.create" in actions
    assert "document.version.upload" in actions
