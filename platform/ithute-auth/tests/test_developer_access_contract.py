"""Developer access requests are identity-scoped and approval gated."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = ROOT / "app/account.py"
MODEL = ROOT / "app/models.py"
MIGRATION = ROOT / "alembic/versions/0013_developer_access_requests.py"

def test_request_endpoint_requires_identity_and_does_not_grant_automatically():
    source=ACCOUNT.read_text()
    assert '@router.post("/developer/access-requests", status_code=201)' in source
    assert "context: AuthContext = Depends(authenticated_context)" in source
    assert 'status="pending"' in source
    assert "DeveloperAccessRequest.user_id == context.user.id" in source
    assert 'status_code=409' in source

def test_migration_has_single_correct_parent():
    source=MIGRATION.read_text()
    assert 'revision = "0013_developer_access_requests"' in source
    assert 'down_revision = "0012_app_redirect_uris"' in source
    assert "developer_access_requests" in source

def test_requests_are_linked_to_users():
    source=MODEL.read_text()
    assert 'class DeveloperAccessRequest(Base):' in source
    assert 'ForeignKey("users.id", ondelete="CASCADE")' in source


def test_admin_decisions_are_audited_and_do_not_provision_services():
    source=(ROOT / "app/admin.py").read_text()
    assert '@router.get("/developer/access-requests")' in source
    assert '@router.post("/developer/access-requests/{request_id}/decision")' in source
    assert "Depends(require_admin)" in source
    assert 'item.status!="pending"' in source
    assert 'event_type="developer_access_request_decided"' in source
    assert 'item.status=payload.decision' in source


def test_requests_require_verified_email():
    source=ACCOUNT.read_text()
    assert "if not context.user.email or not context.user.email_verified:" in source
    assert 'detail="verified email required"' in source


def test_access_request_submission_is_daily_rate_limited():
    source=ACCOUNT.read_text()
    assert "DeveloperAccessRequest.created_at >= utcnow() - timedelta(hours=24)" in source
    assert "if len(recent_requests) >= 5:" in source
    assert 'status_code=429, detail="daily request limit reached"' in source
