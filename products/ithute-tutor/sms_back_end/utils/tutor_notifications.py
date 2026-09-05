import logging
from uuid import UUID

from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import Notification, User
from utils.ithute_push import publish_notification

logger = logging.getLogger("ithute_tutor.notifications")

EVENT_POLICIES = {
    "assignment.published": {"push": True, "route": "/student/assignments"},
    "assignment.graded": {"push": True, "route": "/student/results"},
    "admission.decision": {"push": True, "route": "/admissions"},
    "attendance.absent": {"push": True, "route": "/student/attendance"},
    "report.published": {"push": True, "route": "/student/results"},
    "fee.payment_received": {"push": True, "route": "/payments"},
    "transfer.updated": {"push": True, "route": "/transfers"},
    "school.emergency": {"push": True, "route": "/notifications"},
    "library.due": {"push": True, "route": "/student/library"},
}


def notify_user(
    db: Session,
    *,
    school_id: UUID,
    user_id: UUID,
    event: str,
    title: str,
    message: str,
    data: dict | None = None,
) -> None:
    policy = EVENT_POLICIES.get(event, {"push": False, "route": "/notifications"})
    db.add(Notification(
        school_id=school_id,
        user_id=user_id,
        channel="tutor",
        title=title,
        message=message,
        event=event,
    ))
    user = db.get(User, user_id)
    if not policy.get("push") or user is None or user.auth_user_id is None:
        return
    try:
        publish_notification(
            recipient_sub=user.auth_user_id,
            title=title,
            body=message,
            route=policy.get("route"),
            data={"event": event, "school_id": str(school_id), **(data or {})},
            idempotency_key=f"tutor:{event}:{school_id}:{user_id}:{(data or {}).get('id', '')}",
        )
    except Exception as exc:
        # A temporary Push outage must never roll back the school transaction.
        logger.warning("push publish failed event=%s user_id=%s error=%s", event, user_id, type(exc).__name__)
