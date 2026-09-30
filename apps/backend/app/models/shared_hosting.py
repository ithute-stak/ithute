from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class HostingDatabase(Base):
    __tablename__ = "hosting_databases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "engine", "database_name", name="uq_hosting_database_tenant_engine_name"),
        UniqueConstraint("username", name="uq_hosting_database_username"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    engine: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    engine_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    database_name: Mapped[str] = mapped_column(String(63), nullable=False)
    username: Mapped[str] = mapped_column(String(63), nullable=False)
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False)
    pending_encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_host: Mapped[str | None] = mapped_column(String(253), nullable=True)
    internal_port: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(24), default="provision", nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HostingSourceCredential(Base):
    __tablename__ = "hosting_source_credentials"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_hosting_source_credential_project_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(24), nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HostingSource(Base):
    __tablename__ = "hosting_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_source_credentials.id", ondelete="SET NULL"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    repository_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    repository_branch: Mapped[str | None] = mapped_column(String(160), nullable=True)
    repository_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upload_object_key: Mapped[str | None] = mapped_column(String(500), unique=True, nullable=True)
    upload_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upload_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    unpacked_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="registered", nullable=False, index=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
