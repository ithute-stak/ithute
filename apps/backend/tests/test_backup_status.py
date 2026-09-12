import json
from pathlib import Path

from app.core.config import settings
from app.services.backup_status import backup_operational_status, restore_drill_history


def test_backup_status_reports_healthy_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_status_dir", str(tmp_path))
    monkeypatch.setattr(settings, "backup_max_age_seconds", 93600)
    (tmp_path / "last-run.json").write_text(json.dumps({"status": "success", "finished_at": "2999-01-01T00:00:00Z"}), encoding="utf-8")
    (tmp_path / "health.json").write_text(json.dumps({"healthy": True, "snapshot_count": 2}), encoding="utf-8")
    result = backup_operational_status()
    assert result["healthy"] is True
    assert result["severity"] == "ok"
    assert result["reasons"] == []


def test_backup_status_surfaces_operator_alert(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_status_dir", str(tmp_path))
    result = backup_operational_status()
    assert result["healthy"] is False
    assert result["severity"] == "critical"
    assert result["operator_action"]
    assert len(result["reasons"]) == 2


def test_restore_drill_history_is_latest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "backup_status_dir", str(tmp_path))
    path = Path(tmp_path) / "restore-drills.jsonl"
    path.write_text('{"status":"success","snapshot":"one"}\n{"status":"success","snapshot":"two"}\n', encoding="utf-8")
    rows = restore_drill_history(1)
    assert rows == [{"status": "success", "snapshot": "two"}]
