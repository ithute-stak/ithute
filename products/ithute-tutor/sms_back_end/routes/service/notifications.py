from uuid import UUID

from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import Notification
from utils.convex import current_school_id


def create_notification(
    db: Session,
    channel: str,
    title: str,
    message: str,
    event: str,
    *,
    school_id: UUID | None = None,
    user_id: UUID | None = None,
):
    resolved_school_id = school_id
    if resolved_school_id is None:
        context_school = current_school_id.get()
        if context_school:
            resolved_school_id = UUID(str(context_school))

    notification = Notification(
        school_id=resolved_school_id,
        user_id=user_id,
        channel=channel,
        title=title,
        message=message,
        event=event,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
