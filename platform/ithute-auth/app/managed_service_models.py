from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .models import utcnow


class ManagedServiceClient(Base):
    __tablename__ = "managed_service_clients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_audiences_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    allowed_scopes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    credentials: Mapped[list["ManagedServiceCredential"]] = relationship(
        back_populates="service_client",
        cascade="all, delete-orphan",
    )


class ManagedServiceCredential(Base):
    __tablename__ = "managed_service_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    service_client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("managed_service_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secret_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    secret_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    service_client: Mapped[ManagedServiceClient] = relationship(back_populates="credentials")
