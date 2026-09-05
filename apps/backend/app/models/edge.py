import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EdgeApplication(Base):
    __tablename__ = "edge_applications"
    __table_args__ = (UniqueConstraint("tenant_id", "hostname", name="uq_edge_application_tenant_hostname"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(24), default="dns_only", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cache_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    waf_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bot_protection_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    api_shield_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    access_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tls_mode: Mapped[str] = mapped_column(String(24), default="automatic", nullable=False)
    minimum_tls_version: Mapped[str] = mapped_column(String(16), default="TLSv1.2", nullable=False)
    health_path: Mapped[str] = mapped_column(String(500), default="/", nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EdgeOrigin(Base):
    __tablename__ = "edge_origins"
    __table_args__ = (UniqueConstraint("application_id", "name", name="uq_edge_origin_application_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("edge_applications.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    failover_priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    health_path: Mapped[str] = mapped_column(String(500), default="/", nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EdgeRule(Base):
    __tablename__ = "edge_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("edge_applications.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    expression: Mapped[str] = mapped_column(Text, default="true", nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EdgeInspection(Base):
    __tablename__ = "edge_inspections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("edge_applications.id", ondelete="CASCADE"), index=True, nullable=False)
    origin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("edge_origins.id", ondelete="CASCADE"), index=True, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    healthy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tls_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    cipher: Mapped[str | None] = mapped_column(String(120), nullable=True)
    certificate_issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certificate_not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certificate_days_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DnsZoneAnalyticsSnapshot(Base):
    __tablename__ = "dns_zone_analytics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    zone_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    serial: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dnssec_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rrset_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    type_counts_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
