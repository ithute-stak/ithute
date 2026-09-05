import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import AuditLog, User
from app.services.mail_ops import (
    MailOpsError,
    queue_deferred,
    queue_delete,
    queue_flush,
    queue_list,
    queue_retry,
    queue_summary,
    tls_status,
)

router = APIRouter(prefix="/mail/operations", tags=["mail-operations"])
QUEUE_ID_RE = re.compile(r"^[A-F0-9]{5,32}$", re.IGNORECASE)


def _call(fn, *args):
    try:
        return fn(*args)
    except MailOpsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _queue_id(value: str) -> str:
    clean = value.strip().rstrip("*!")
    if not QUEUE_ID_RE.fullmatch(clean):
        raise HTTPException(status_code=422, detail="Invalid Postfix queue ID")
    return clean.upper()


def _audit(db: Session, current: User, action: str, queue_id: str | None = None) -> None:
    db.add(
        AuditLog(
            actor_user_id=current.id,
            action=action,
            resource_type="mail_queue",
            resource_id=queue_id,
            metadata_json=json.dumps({"queue_id": queue_id} if queue_id else {}, sort_keys=True),
        )
    )
    db.commit()


@router.get("/queue")
def list_queue(current: User = Depends(require_platform_owner)):
    result = _call(queue_list)
    return {"items": result.get("items", []), "total": len(result.get("items", []))}


@router.get("/queue/deferred")
def list_deferred_queue(current: User = Depends(require_platform_owner)):
    result = _call(queue_deferred)
    return {"items": result.get("items", []), "total": result.get("total", len(result.get("items", [])))}


@router.get("/queue/summary")
def queue_status(current: User = Depends(require_platform_owner)):
    return _call(queue_summary)


@router.get("/tls/status")
def mail_tls_status(current: User = Depends(require_platform_owner)):
    return _call(tls_status)


@router.post("/queue/flush")
def flush_queue(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    result = _call(queue_flush)
    _audit(db, current, "mail.queue.flush")
    return result


@router.post("/queue/{queue_id}/retry")
def retry_queue_item(queue_id: str, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    clean = _queue_id(queue_id)
    result = _call(queue_retry, clean)
    _audit(db, current, "mail.queue.retry", clean)
    return result


@router.delete("/queue/{queue_id}")
def delete_queue_item(queue_id: str, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    clean = _queue_id(queue_id)
    result = _call(queue_delete, clean)
    _audit(db, current, "mail.queue.delete", clean)
    return result
