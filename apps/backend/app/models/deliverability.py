import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DkimKey(Base):
    __tablename__ = "dkim_keys"
    __table_args__ = (UniqueConstraint("domain_id", "selector", name="uq_dkim_domain_selector"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=False)
    selector: Mapped[str] = mapped_column(String(63), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), default="rsa-sha256", nullable=False)
    public_key_b64: Mapped[str] = mapped_column(String(4096), nullable=False)
    private_key_encrypted: Mapped[str] = mapped_column(String(8192), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
