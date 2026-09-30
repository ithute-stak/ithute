from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class HostingBuildLog(Base):
    __tablename__ = "hosting_build_logs"
    __table_args__ = (
        UniqueConstraint("build_id", "sequence", name="uq_hosting_build_log_sequence"),
        CheckConstraint("level IN ('info','warning','error')", name="ck_hosting_build_log_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    build_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_builds.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(48), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
