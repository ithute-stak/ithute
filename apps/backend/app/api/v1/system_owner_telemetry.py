from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import require_platform_owner
from app.models import User
from app.services.backup_status import BackupStatusError, backup_operational_status, restore_drill_history
from app.services.infrastructure_telemetry import InfrastructureTelemetryError, live_infrastructure_telemetry


router = APIRouter(prefix="/platform/ithute/system-owner", tags=["system-owner-telemetry"])


def _live() -> dict[str, Any]:
    try:
        return live_infrastructure_telemetry()
    except InfrastructureTelemetryError as exc:
        return {
            "status": "unavailable",
            "sampled_at": None,
            "host": {},
            "containers": [],
            "container_count": 0,
            "error": str(exc),
        }


@router.get("/live-infrastructure")
def live_infrastructure(
    current: User = Depends(require_platform_owner),
) -> dict:
    _ = current
    return _live()


@router.get("/operations")
def owner_operations(
    current: User = Depends(require_platform_owner),
) -> dict[str, Any]:
    _ = current
    telemetry = _live()
    alerts: list[dict[str, str]] = []
    host = telemetry.get("host") or {}

    if telemetry.get("status") == "unavailable":
        alerts.append({
            "severity": "high",
            "source": "infrastructure",
            "title": "Live infrastructure telemetry unavailable",
            "detail": telemetry.get("error") or "Prometheus could not be queried from the control plane.",
        })
    else:
        for label, key in (("CPU", "cpu_percent"), ("Memory", "memory_percent"), ("Disk", "disk_percent")):
            value = host.get(key)
            if not isinstance(value, (int, float)):
                continue
            if value >= 95:
                alerts.append({
                    "severity": "critical",
                    "source": "infrastructure",
                    "title": f"VPS {label} usage is {value:.1f}%",
                    "detail": "Immediate intervention is required before production capacity is exhausted.",
                })
            elif value >= 80:
                alerts.append({
                    "severity": "warning",
                    "source": "infrastructure",
                    "title": f"VPS {label} usage is {value:.1f}%",
                    "detail": "Capacity has crossed the owner warning threshold.",
                })

    try:
        backup = backup_operational_status()
    except BackupStatusError as exc:
        backup = {"healthy": False, "severity": "critical", "reasons": [str(exc)], "checked_at": None}

    if not backup.get("healthy", False):
        reasons = backup.get("reasons") or ["Backup status is unhealthy."]
        alerts.append({
            "severity": "critical",
            "source": "backups",
            "title": "Backup or recovery assurance needs attention",
            "detail": "; ".join(str(reason) for reason in reasons),
        })

    try:
        drills = restore_drill_history(10)
    except BackupStatusError:
        drills = []
    latest_drill = drills[0] if drills else None
    if not latest_drill:
        alerts.append({
            "severity": "warning",
            "source": "recovery",
            "title": "No restore drill has been recorded",
            "detail": "A backup is not fully trusted until a controlled restore has been verified.",
        })
    elif str(latest_drill.get("status", "")).lower() not in {"success", "passed", "ok"}:
        alerts.append({
            "severity": "critical",
            "source": "recovery",
            "title": "Latest restore drill did not pass",
            "detail": str(latest_drill.get("error") or latest_drill.get("message") or "Inspect the most recent recovery drill result."),
        })

    severity_order = {"critical": 0, "high": 1, "warning": 2, "medium": 2, "info": 3}
    alerts.sort(key=lambda item: severity_order.get(item.get("severity", "info"), 9))
    return {
        "status": "critical" if any(item["severity"] in {"critical", "high"} for item in alerts) else ("warning" if alerts else "ok"),
        "alerts": alerts,
        "live_infrastructure": telemetry,
        "backup": backup,
        "restore_drills": drills,
    }
