from pathlib import Path


def test_phase22_compliance_policy_control_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    api = (root / "app/api/v1/compliance.py").read_text(encoding="utf-8")
    models = (root / "app/models/compliance.py").read_text(encoding="utf-8")
    migration = (root / "alembic/versions/0023_phase22_compliance.py").read_text(encoding="utf-8")
    assert 'revision = "0023_phase22_compliance"' in migration
    assert 'down_revision = "0022_phase21_comms"' in migration
    for table in ("compliance_policies", "compliance_obligations", "compliance_reviews", "compliance_audit_events"):
        assert table in models and table in migration
    for control in ("COMPLIANCE_POLICY", "COMPLIANCE_REVIEW", "Self-approval is disabled", "non-compliant review"):
        assert control in api
