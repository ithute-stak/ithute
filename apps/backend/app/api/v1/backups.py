from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_platform_owner
from app.models import User
from app.services.backup_status import BackupStatusError, backup_operational_status, restore_drill_history

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("/status")
def backup_status(current: User = Depends(require_platform_owner)):
    return backup_operational_status()


@router.get("/restore-drills")
def backup_restore_drills(
    limit: int = Query(default=20, ge=1, le=100),
    current: User = Depends(require_platform_owner),
):
    try:
        return {"items": restore_drill_history(limit)}
    except BackupStatusError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
