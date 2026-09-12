import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings


class BackupStatusError(RuntimeError):
    pass


def _root() -> Path:
    return Path(settings.backup_status_dir)


def _read_json(path: Path) -> dict | None:
    try:
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def backup_operational_status() -> dict:
    root = _root()
    last_run = _read_json(root / "last-run.json")
    health = _read_json(root / "health.json")
    now = datetime.now(timezone.utc)
    reasons: list[str] = []

    if health is None:
        reasons.append("backup health metadata is unavailable")
    elif not health.get("healthy", False):
        reasons.append("latest restore point is stale or repository health failed")

    if last_run is None:
        reasons.append("scheduled backup run metadata is unavailable")
    elif last_run.get("status") != "success":
        reasons.append("most recent scheduled backup failed")

    last_success = _parse_time((last_run or {}).get("finished_at"))
    age_seconds = None
    if last_success:
        age_seconds = max(0, int((now - last_success).total_seconds()))

    healthy = not reasons
    severity = "ok" if healthy else "critical"
    return {
        "healthy": healthy,
        "severity": severity,
        "reasons": reasons,
        "operator_action": None if healthy else "Inspect backup-scheduler logs, repository access, and run the documented restore drill before clearing the alert.",
        "last_run": last_run,
        "repository_health": health,
        "last_success_age_seconds": age_seconds,
        "max_age_seconds": settings.backup_max_age_seconds,
        "checked_at": now.isoformat(),
    }


def restore_drill_history(limit: int = 20) -> list[dict]:
    path = _root() / "restore-drills.jsonl"
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    except OSError as exc:
        raise BackupStatusError("Unable to read restore-drill history") from exc
    return rows[-limit:][::-1]
