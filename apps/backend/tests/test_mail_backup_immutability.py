from pathlib import Path


def test_mail_node_retention_refuses_immutable_snapshot_deletion():
    source = (Path(__file__).parents[1] / "app" / "api" / "v1" / "mail_node_operations.py").read_text(encoding="utf-8")
    assert "snapshot.immutable_until is not None and snapshot.immutable_until > now" in source
    assert "continue" in source


def test_manual_and_scheduled_snapshots_get_immutable_until():
    root = Path(__file__).parents[1] / "app" / "api" / "v1"
    operations = (root / "mail_node_operations.py").read_text(encoding="utf-8")
    agent = (root / "mail_node_agent.py").read_text(encoding="utf-8")
    assert "immutable_until=now + timedelta(days=" in operations
    assert "immutable_until=now + timedelta(days=" in agent


def test_backup_policy_exposes_immutability_days():
    source = (Path(__file__).parents[1] / "app" / "api" / "v1" / "hosting.py").read_text(encoding="utf-8")
    assert "immutability_days: int = Field(default=7, ge=1, le=365)" in source
    assert '"backup_immutability_days": row.backup_immutability_days' in source
