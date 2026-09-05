import logging
import uuid

from sqlalchemy import Column, DateTime, String, UUID, event, func, inspect
from sqlalchemy.orm import declarative_base

from utils.convex import current_user_id

logger = logging.getLogger("ithute_tutor.audit")
Declaration = declarative_base()


class CustomBase:
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(36), nullable=True)
    updated_by = Column(String(36), nullable=True)


class Base(CustomBase, Declaration):
    __abstract__ = True


def _record_id(target):
    value = getattr(target, "id", None)
    return str(value) if value is not None else "pending"


def set_created_by(mapper, connection, target):
    user_id = current_user_id.get()
    if user_id:
        target.created_by = user_id
        target.updated_by = user_id
    logger.info(
        "db.insert table=%s record_id=%s actor=%s",
        target.__tablename__,
        _record_id(target),
        user_id or "system",
    )


def set_updated_by(mapper, connection, target):
    user_id = current_user_id.get()
    if user_id:
        target.updated_by = user_id
    state = inspect(target)
    changed_columns = [attr.key for attr in state.attrs if attr.history.has_changes()]
    logger.info(
        "db.update table=%s record_id=%s actor=%s changed_columns=%s",
        target.__tablename__,
        _record_id(target),
        user_id or "system",
        ",".join(changed_columns) or "none",
    )


def before_delete(mapper, connection, target):
    user_id = current_user_id.get()
    logger.info(
        "db.delete table=%s record_id=%s actor=%s",
        target.__tablename__,
        _record_id(target),
        user_id or "system",
    )


event.listen(Base, "before_insert", set_created_by, propagate=True)
event.listen(Base, "before_update", set_updated_by, propagate=True)
event.listen(Base, "before_delete", before_delete, propagate=True)
