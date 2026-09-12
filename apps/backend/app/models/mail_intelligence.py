from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MailRetentionPolicy(Base):
    __tablename__ = "mail_retention_policies"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_mail_retention_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2555)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    immutable_archive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mailbox_scope_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DmarcAggregateReport(Base):
    __tablename__ = "dmarc_aggregate_reports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "report_id", name="uq_dmarc_tenant_report"),
        Index("ix_dmarc_tenant_begin", "tenant_id", "period_begin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    report_id: Mapped[str] = mapped_column(String(255), nullable=False)
    reporter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    period_begin: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aligned_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sources_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PhishingFinding(Base):
    __tablename__ = "phishing_findings"
    __table_args__ = (Index("ix_phishing_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    mailbox_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("mailboxes.id", ondelete="SET NULL"), nullable=True)
    message_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    finding_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sender: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    indicators_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    action_taken: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MailAutomationRule(Base):
    __tablename__ = "mail_automation_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_mail_automation_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_event: Mapped[str] = mapped_column(String(160), nullable=False, default="mail.received")
    conditions_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
