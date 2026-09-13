from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

HOSTING_RUNTIME_MANIFEST_VERSION = "1"


class HostingNodeAgent(Base):
    __tablename__ = "hosting_node_agents"

    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="CASCADE"), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_hint: Mapped[str] = mapped_column(String(24), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rotated_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)


class HostingEnvironmentVariable(Base):
    __tablename__ = "hosting_environment_variables"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_hosting_env_project_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HostingDeployment(Base):
    __tablename__ = "hosting_deployments"
    __table_args__ = (UniqueConstraint("project_id", "release_number", name="uq_hosting_deployment_project_release"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    previous_deployment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_deployments.id", ondelete="SET NULL"), nullable=True)
    release_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_ref: Mapped[str] = mapped_column(String(500), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    source_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_manifest_version: Mapped[str] = mapped_column(String(16), default=HOSTING_RUNTIME_MANIFEST_VERSION, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
