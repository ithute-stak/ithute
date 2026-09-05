from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ProductOperationalStatus(str, enum.Enum):
    unknown = "unknown"
    online = "online"
    degraded = "degraded"
    maintenance = "maintenance"
    offline = "offline"


class PlatformEventStatus(str, enum.Enum):
    accepted = "accepted"
    processing = "processing"
    delivered = "delivered"
    failed = "failed"


class SubscriptionGrantStatus(str, enum.Enum):
    demo = "demo"
    active = "active"
    suspended = "suspended"
    expired = "expired"


class DeploymentStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    rolled_back = "rolled_back"


class BackupStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    ready = "ready"
    failed = "failed"
    expired = "expired"


class SecuritySeverity(str, enum.Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class IthuteProduct(Base):
    __tablename__ = "ithute_products"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="business")
    manifest_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    operational_status: Mapped[ProductOperationalStatus] = mapped_column(
        Enum(ProductOperationalStatus, name="product_operational_status"),
        nullable=False,
        default=ProductOperationalStatus.unknown,
    )
    public_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    health_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    deployment_target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deployment_mode: Mapped[str] = mapped_column(String(80), nullable=False, default="isolated")
    database_ownership: Mapped[str] = mapped_column(String(80), nullable=False, default="product")
    database_engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    auth_mode: Mapped[str] = mapped_column(String(80), nullable=False, default="central")
    push_mode: Mapped[str] = mapped_column(String(80), nullable=False, default="central")
    realtime_mode: Mapped[str] = mapped_column(String(80), nullable=False, default="central")
    event_bus_mode: Mapped[str] = mapped_column(String(80), nullable=False, default="central")
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class IthuteProductHeartbeat(Base):
    __tablename__ = "ithute_product_heartbeats"
    __table_args__ = (Index("ix_ithute_product_heartbeats_product_observed", "product_id", "observed_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[str] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[ProductOperationalStatus] = mapped_column(
        Enum(ProductOperationalStatus, name="product_operational_status", create_type=False),
        nullable=False,
    )
    version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    database_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    auth_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    push_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    realtime_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    container_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IthutePlatformEvent(Base):
    __tablename__ = "ithute_platform_events"
    __table_args__ = (
        UniqueConstraint("product_id", "source_event_id", name="uq_ithute_event_product_source"),
        Index("ix_ithute_platform_events_type_created", "event_type", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[str] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False, index=True)
    source_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tenant_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[PlatformEventStatus] = mapped_column(
        Enum(PlatformEventStatus, name="platform_event_status"),
        nullable=False,
        default=PlatformEventStatus.accepted,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IthutePlatformNotification(Base):
    __tablename__ = "ithute_platform_notifications"
    __table_args__ = (Index("ix_ithute_notification_recipient_created", "recipient_sub", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_sub: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ithute_platform_events.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    action_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IthuteSubscriptionGrant(Base):
    __tablename__ = "ithute_subscription_grants"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "product_id", name="uq_ithute_subscription_subject_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    product_id: Mapped[str] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False)
    plan: Mapped[str] = mapped_column(String(100), nullable=False, default="demo")
    status: Mapped[SubscriptionGrantStatus] = mapped_column(
        Enum(SubscriptionGrantStatus, name="subscription_grant_status"),
        nullable=False,
        default=SubscriptionGrantStatus.demo,
    )
    features_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class IthuteProductCommand(Base):
    __tablename__ = "ithute_product_commands"
    __table_args__ = (Index("ix_ithute_commands_product_created", "product_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[str] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False)
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IthuteProductDeployment(Base):
    __tablename__ = "ithute_product_deployments"
    __table_args__ = (Index("ix_ithute_deployments_product_started", "product_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[str] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    environment: Mapped[str] = mapped_column(String(50), nullable=False, default="production")
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, name="deployment_status"),
        nullable=False,
        default=DeploymentStatus.queued,
    )
    initiated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    backup_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IthuteProductBackup(Base):
    __tablename__ = "ithute_product_backups"
    __table_args__ = (Index("ix_ithute_backups_product_created", "product_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[str] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, default="database")
    status: Mapped[BackupStatus] = mapped_column(
        Enum(BackupStatus, name="backup_status"),
        nullable=False,
        default=BackupStatus.pending,
    )
    storage_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    restore_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IthuteSecurityEvent(Base):
    __tablename__ = "ithute_security_events"
    __table_args__ = (Index("ix_ithute_security_product_created", "product_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("ithute_products.id", ondelete="SET NULL"), nullable=True)
    severity: Mapped[SecuritySeverity] = mapped_column(
        Enum(SecuritySeverity, name="security_severity"),
        nullable=False,
        default=SecuritySeverity.info,
    )
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IthuteSecretReference(Base):
    __tablename__ = "ithute_secret_references"
    __table_args__ = (UniqueConstraint("product_id", "name", name="uq_ithute_secret_product_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="docker_secret")
    reference: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    rotation_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IthuteDeveloperClient(Base):
    __tablename__ = "ithute_developer_clients"
    __table_args__ = (UniqueConstraint("client_id", name="uq_ithute_developer_client_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed_products_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scopes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IthuteWebhookSubscription(Base):
    __tablename__ = "ithute_webhook_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    developer_client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ithute_developer_clients.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str | None] = mapped_column(ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=True)
    event_pattern: Mapped[str] = mapped_column(String(160), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ithute_secret_references.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IthuteSupportContext(Base):
    __tablename__ = "ithute_support_contexts"
    __table_args__ = (UniqueConstraint("support_ticket_id", name="uq_ithute_support_context_ticket"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    support_ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("ithute_products.id", ondelete="SET NULL"), nullable=True)
    organization_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
