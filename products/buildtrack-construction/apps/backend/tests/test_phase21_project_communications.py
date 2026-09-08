from pathlib import Path


def test_phase21_project_communications_contract_is_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    api = (root / "app/api/v1/communications.py").read_text(encoding="utf-8")
    models = (root / "app/models/communications.py").read_text(encoding="utf-8")
    migration = (root / "alembic/versions/0022_phase21_comms.py").read_text(encoding="utf-8")
    assert 'revision = "0022_phase21_comms"' in migration
    assert 'down_revision = "0021_phase20_resources"' in migration
    for table in ("project_stakeholders", "project_correspondence", "project_meetings", "meeting_actions", "communication_audit_events"):
        assert table in models and table in migration
    for control in ("FORMAL_CORRESPONDENCE", "MEETING_MINUTES", "record-dispatch", "Self-verification is disabled", "communications.action.verified"):
        assert control in api
