from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class InfrastructureCommercialProfile(Base):
    """Owner-maintained cost and capacity truth for an infrastructure server."""

    __tablename__ = "infrastructure_commercial_profiles"
    __table_args__ = (UniqueConstraint("server_id", name="uq_infrastructure_commercial_server"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("infrastructure_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(3), default="LSL", nullable=False)
    provider_cost_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    backup_cost_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bandwidth_cost_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    other_cost_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cpu_millicores: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_memory_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_storage_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    included_bandwidth_gb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_margin_bps: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantInfrastructureAllocation(Base):
    """Auditable customer share of a server used for capacity and cost allocation."""

    __tablename__ = "tenant_infrastructure_allocations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "server_id", name="uq_tenant_infrastructure_allocation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allocation_weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cpu_millicores: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bandwidth_gb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
