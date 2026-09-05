from sqlalchemy import Boolean, Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from database.base import Base


class Notification(Base):
    __tablename__ = "notifications"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    channel = Column(String(255), default="finance", index=True)
    title = Column(String(255))
    message = Column(Text)
    event = Column(String(100))
    is_read = Column(Boolean, default=False)
