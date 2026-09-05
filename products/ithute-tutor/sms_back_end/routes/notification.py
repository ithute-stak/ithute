from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import Notification, User
from database.session import get_db
from utils.auth.tokens import get_current_user
from utils.school_context import SchoolContext, get_school_context

router = APIRouter(prefix="/notifications", tags=["Notification"])

_ADMIN_ROLES = {"school_admin", "principal", "vice_principal", "super_admin"}


def _visible_notifications(db: Session, current_user: User, context: SchoolContext):
    query = db.query(Notification).filter(Notification.school_id == context.school_id)
    if context.is_platform_admin or context.role in _ADMIN_ROLES:
        return query

    return query.filter(
        or_(
            Notification.user_id == current_user.id,
            Notification.channel == current_user.channel,
        )
    )


@router.get("/")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    return _visible_notifications(db, current_user, context).order_by(Notification.created_at.desc()).all()


@router.put("/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    notifications = _visible_notifications(db, current_user, context).filter(Notification.is_read.is_(False)).all()
    for notification in notifications:
        notification.is_read = True
    db.commit()
    return {"message": "All notifications marked as read", "count": len(notifications)}


@router.delete("/clear")
def clear_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    notifications = _visible_notifications(db, current_user, context).all()
    count = len(notifications)
    for notification in notifications:
        db.delete(notification)
    db.commit()
    return {"message": "Notifications cleared successfully", "count": count}


@router.put("/{notification_id}/read")
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    notification = _visible_notifications(db, current_user, context).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.get("/{notification_id}")
def get_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    notification = _visible_notifications(db, current_user, context).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return notification


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context: SchoolContext = Depends(get_school_context),
):
    notification = _visible_notifications(db, current_user, context).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    db.delete(notification)
    db.commit()
    return {"message": "Notification deleted successfully"}
