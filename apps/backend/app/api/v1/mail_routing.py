from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import User
from app.services.mail_routing_sync import MailRoutingSyncError, build_mail_routing, sync_mail_routing

router = APIRouter(prefix="/platform/mail-routing", tags=["mail-routing"])


@router.get("")
def mail_routing_status(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        routes = build_mail_routing(db)
    except MailRoutingSyncError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "relay_domains": len(routes["relay_domains"]),
        "relay_recipients": len(routes["relay_recipients"]),
        "transport_routes": len(routes["transport"]),
        "virtual_aliases": len(routes["virtual_aliases"]),
    }


@router.post("/reconcile")
def reconcile_mail_routing(
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    try:
        counts = sync_mail_routing(db)
    except MailRoutingSyncError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Unable to write mail routing maps") from exc
    return {"reconciled": True, **counts}
