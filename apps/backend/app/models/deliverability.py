import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DkimKey(Base):
    __tablename__ = "dkim_keys"
    __table_args__ = (UniqueConstraint("domain_id", "selector", name="uq_dkim_domain_selector"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=False)
    selector: Mapped[str] = mapped_column(String(63), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(32), default="rsa-sha256", nullable=False)
    public_key_b64: Mapped[str] = mapped_column(String(4096), nullable=False)
    private_key_encrypted: Mapped[str] = mapped_column(String(8192), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)



class DmarcAggregateReport(Base):
    __tablename__ = "dmarc_aggregate_reports"
    __table_args__ = (
        UniqueConstraint("domain_id", "reporter_org", "report_id", name="uq_dmarc_domain_report"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=False)
    reporter_org: Mapped[str] = mapped_column(String(255), nullable=False)
    reporter_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    report_id: Mapped[str] = mapped_column(String(512), nullable=False)
    period_begin: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    policy_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    policy_p: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_sp: Mapped[str | None] = mapped_column(String(32), nullable=True)
    policy_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    total_messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_rate_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    parser_engine: Mapped[str] = mapped_column(String(32), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), default="1", nullable=False)
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DmarcAggregateSource(Base):
    __tablename__ = "dmarc_aggregate_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dmarc_aggregate_reports.id", ondelete="CASCADE"), index=True, nullable=False)
    source_ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disposition: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dkim_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    spf_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    header_from: Mapped[str | None] = mapped_column(String(253), nullable=True)
    envelope_from: Mapped[str | None] = mapped_column(String(253), nullable=True)
    dmarc_pass: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
