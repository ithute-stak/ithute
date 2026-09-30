from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class HostingSourceWebhook(Base):
    __tablename__ = "hosting_source_webhooks"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_hosting_source_webhook_source"),
        CheckConstraint("provider IN ('github','gitlab','bitbucket','generic')", name="ck_hosting_source_webhook_provider"),
        CheckConstraint("status IN ('active','disabled')", name="ck_hosting_source_webhook_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_sources.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    pending_rebuild: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pending_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HostingWebhookDelivery(Base):
    __tablename__ = "hosting_webhook_deliveries"
    __table_args__ = (UniqueConstraint("webhook_id", "delivery_id", name="uq_hosting_webhook_delivery"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_source_webhooks.id", ondelete="CASCADE"), nullable=False, index=True)
    delivery_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_name: Mapped[str] = mapped_column(String(80), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
