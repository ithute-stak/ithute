import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PlatformConfiguration(Base):
    """Singleton platform bootstrap/domain configuration.

    This is deliberately separate from tenant domains.  The platform owner can
    start the control plane on a public IP, then later turn a purchased domain
    into the platform's own authoritative DNS + HTTPS identity.
    """

    __tablename__ = "platform_configuration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="bootstrap")
    security_level: Mapped[str] = mapped_column(String(32), nullable=False, default="bootstrap")
    bootstrap_public_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    primary_domain: Mapped[str | None] = mapped_column(String(253), nullable=True, unique=True)
    panel_hostname: Mapped[str | None] = mapped_column(String(253), nullable=True)
    api_hostname: Mapped[str | None] = mapped_column(String(253), nullable=True)
    groupware_hostname: Mapped[str | None] = mapped_column(String(253), nullable=True)
    mail_hostname: Mapped[str | None] = mapped_column(String(253), nullable=True)
    nameserver_1: Mapped[str | None] = mapped_column(String(253), nullable=True)
    nameserver_2: Mapped[str | None] = mapped_column(String(253), nullable=True)
    nameserver_1_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nameserver_2_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acme_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    dns_zone_provisioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delegation_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
