from fastapi import APIRouter, Depends

from app.api.deps import require_platform_owner
from app.models import User
from app.services.infrastructure_telemetry import InfrastructureTelemetryError, live_infrastructure_telemetry


router = APIRouter(prefix="/platform/ithute/system-owner", tags=["system-owner-telemetry"])


@router.get("/live-infrastructure")
def live_infrastructure(
    current: User = Depends(require_platform_owner),
) -> dict:
    _ = current
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
