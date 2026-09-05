import uuid
from datetime import datetime

from sqlalchemy import Column, String, ForeignKey, Boolean, DateTime, UUID
from sqlalchemy.orm import relationship

from database.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    jti = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    revoked = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    user = relationship("User", back_populates="refresh_tokens")
