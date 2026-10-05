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



class HostingDatabaseReplica(Base):
    __tablename__ = "hosting_database_replicas"
    __table_args__ = (
        UniqueConstraint("database_id", "node_id", name="uq_hosting_database_replica_database_node"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    database_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(24), default="replica", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="planned", nullable=False, index=True)
    healthy: Mapped[bool] = mapped_column(default=False, nullable=False)
    lag_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    lag_seconds: Mapped[float | None] = mapped_column(nullable=True)
    receive_lsn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replay_lsn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    in_recovery: Mapped[bool | None] = mapped_column(nullable=True)
    telemetry_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)



class HostingDatabaseFailoverAttempt(Base):
    __tablename__ = "hosting_database_failover_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    database_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    replica_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_database_replicas.id", ondelete="RESTRICT"), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="requested", nullable=False, index=True)
    source_fence_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_promote_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_fenced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    failure_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fence_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promotion_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    service_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redundancy_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger: Mapped[str] = mapped_column(String(24), default="manual", nullable=False)
    rto_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rto_met: Mapped[bool | None] = mapped_column(nullable=True)
    repair_slo_met: Mapped[bool | None] = mapped_column(nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)



class HostingPostgresReplicationGroup(Base):
    __tablename__ = "hosting_postgres_replication_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    primary_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    rpo_class: Mapped[str] = mapped_column(String(24), default="async", nullable=False)
    required_sync_standbys: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rpo_healthy: Mapped[bool] = mapped_column(default=True, nullable=False)
    observed_synchronous_commit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observed_sync_standbys: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rpo_last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_failover_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    rto_target_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    detection_budget_seconds: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    fencing_budget_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    promotion_budget_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    repair_budget_seconds: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HostingPostgresReplicationMember(Base):
    __tablename__ = "hosting_postgres_replication_members"
    __table_args__ = (
        UniqueConstraint("database_id", name="uq_pg_replication_member_database"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), primary_key=True)
    database_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_databases.id", ondelete="CASCADE"), primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class HostingPostgresReplicationStandby(Base):
    __tablename__ = "hosting_postgres_replication_standbys"
    __table_args__ = (
        UniqueConstraint("group_id", "node_id", name="uq_pg_replication_standby_group_node"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)
    healthy: Mapped[bool] = mapped_column(default=False, nullable=False)
    receive_lsn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replay_lsn: Mapped[str | None] = mapped_column(String(64), nullable=True)
    replay_backlog_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    replay_age_seconds: Mapped[float | None] = mapped_column(nullable=True)
    in_recovery: Mapped[bool | None] = mapped_column(nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telemetry_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)



class HostingPostgresGroupFailoverAttempt(Base):
    __tablename__ = "hosting_postgres_group_failovers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    standby_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_postgres_replication_standbys.id", ondelete="RESTRICT"), nullable=False)
    source_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    target_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="requested", nullable=False, index=True)
    source_fence_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_promote_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_fenced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)



class HostingPostgresTopologyRepair(Base):
    __tablename__ = "hosting_postgres_topology_repairs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False)
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class HostingPostgresRpoPolicyOperation(Base):
    __tablename__ = "hosting_postgres_rpo_policy_ops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_postgres_replication_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="RESTRICT"), nullable=False, index=True)
    rpo_class: Mapped[str] = mapped_column(String(24), nullable=False)
    required_sync_standbys: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
