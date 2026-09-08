from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"


def test_phase5_routes_and_migration_are_registered() -> None:
    router = (BACKEND / "app/api/v1/router.py").read_text()
    models = (BACKEND / "app/models/__init__.py").read_text()
    migration = (BACKEND / "alembic/versions/0006_phase5_tender_management.py").read_text()
    evidence_migration = (BACKEND / "alembic/versions/0007_phase5_submission_approval_evidence.py").read_text()
    tender_model = (BACKEND / "app/models/tender.py").read_text()
    api = (BACKEND / "app/api/v1/tenders.py").read_text()
    admin = (BACKEND / "app/api/v1/tenders_admin.py").read_text()
    assert "tender_admin_router" in router and "tender_router" in router
    assert router.index("include_router(tender_admin_router") < router.index("include_router(tender_router")
    assert '"phase_5"' in router
    assert "TenderEstimateItem" in models and "TenderOutcome" in models
    assert 'down_revision = "0005_phase4_fleet_plant"' in migration
    assert 'revision = "0006_phase5_tender_management"' in migration
    assert 'down_revision = "0006_phase5_tender_management"' in evidence_migration
    assert 'revision = "0007_phase5_submission_evidence"' in evidence_migration
    assert "approval_request_id" in evidence_migration and "approval_request_id" in tender_model
    for table in ("tenders", "tender_checklist_items", "tender_estimate_items", "tender_securities", "tender_clarifications", "tender_submissions", "tender_outcomes", "tender_audit_events"):
        assert f'"{table}"' in migration
    assert 'APIRouter(prefix="/tenders"' in api
    assert '"TENDER_COMMERCIAL"' in api and '"TENDER_SUBMISSION"' in api
    assert "ApprovalRequest" in api and "ApprovalAction" in api
    assert '"/exports/pipeline.csv"' in admin
    assert '@router.post("/bootstrap")' in admin
    assert '@router.post("/{tender_id}/submission-approval")' in admin
    assert '@router.post("/{tender_id}/submit"' in admin
    assert "approval_request_id=approval.id" in admin
    assert "minimum_margin_pct" in admin and "pricing_locked" in admin
    assert "mobilisation-handoff" in api


def test_phase5_browser_workspaces_cover_operational_and_control_contracts() -> None:
    page = (FRONTEND / "app/tenders/page.tsx").read_text()
    control = (FRONTEND / "app/tenders/control/page.tsx").read_text()
    layout = (FRONTEND / "app/layout.tsx").read_text()
    for text in (
        "Tender Management",
        "Document checklist",
        "BOQ / estimate",
        "Securities",
        "Clarifications",
        "Approvals & submission",
        "/tenders/dashboard/summary",
        "/tenders/dashboard/alerts",
        "/tenders/exports/pipeline.csv",
        "Request commercial approval",
        "Request submission approval",
        "Record controlled submission",
    ):
        assert text in page
    for text in (
        "Tender Control",
        "/tenders/policy/current",
        "/tenders/approvals/",
        "Award / loss analysis",
        "Phase 6 mobilisation handoff",
        "Generate Phase 6 handoff",
    ):
        assert text in control
    assert 'href="/tenders"' in layout and 'href="/tenders/control"' in layout
