from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_platform_owner
from app.models import User
from app.services.operations_status import OperationsStatusError, operations_status, slo_status

router = APIRouter(prefix="/operations", tags=["operations"])


def _safe(call):
    try:
        return call()
    except OperationsStatusError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/status")
def platform_operations_status(current: User = Depends(require_platform_owner)):
    return _safe(operations_status)


@router.get("/slo")
def platform_slo_status(current: User = Depends(require_platform_owner)):
    return _safe(slo_status)
