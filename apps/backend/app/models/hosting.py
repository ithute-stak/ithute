from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


HOSTING_RULES_VERSION = "2026-09-13"


class HostingNode(Base):
    """A system-owner controlled allocation boundary on a hosting server.

    Capacity is the amount Ithute is allowed to sell, not necessarily every byte
    or CPU cycle physically present on the machine. This lets the owner reserve
    headroom for the control plane, DNS, mail and the operating system.
    """

    __tablename__ = "hosting_nodes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    public_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    allocatable_storage_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    allocatable_memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    allocatable_cpu_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    accepts_new_projects: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HostingProject(Base):
    __tablename__ = "hosting_projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_hosting_project_tenant_slug"),
        UniqueConstraint("hostname", name="uq_hosting_project_hostname"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    domain_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(253), nullable=True)
    runtime: Mapped[str] = mapped_column(String(32), nullable=False)
    source_repository: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_branch: Mapped[str] = mapped_column(String(160), default="main", nullable=False)
    build_command: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    start_command: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    image_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    container_port: Mapped[int] = mapped_column(Integer, default=8080, nullable=False)
    health_path: Mapped[str] = mapped_column(String(500), default="/", nullable=False)
    storage_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    cpu_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    pid_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="configured", nullable=False, index=True)
    failover_policy: Mapped[str] = mapped_column(String(32), default="manual", nullable=False, index=True)
    rules_version: Mapped[str] = mapped_column(String(32), default=HOSTING_RULES_VERSION, nullable=False)
    rules_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rules_accepted_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)



class HostingResourceReservation(Base):
    """Temporary capacity hold used before a workload becomes an allocation."""

    __tablename__ = "hosting_resource_reservations"
    __table_args__ = (
        CheckConstraint("cpu_millicores >= 0", name="ck_hosting_resource_reservation_cpu_nonnegative"),
        CheckConstraint("memory_mb >= 0", name="ck_hosting_resource_reservation_memory_nonnegative"),
        CheckConstraint("storage_mb >= 0", name="ck_hosting_resource_reservation_storage_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(80), default="placement", nullable=False)
    cpu_millicores: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
