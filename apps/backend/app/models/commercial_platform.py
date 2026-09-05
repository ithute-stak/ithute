import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MailboxDelegate(Base):
    __tablename__ = "mailbox_delegates"
    __table_args__ = (UniqueConstraint("mailbox_id", "delegate_address", name="uq_mailbox_delegate"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True, nullable=False)
    delegate_address: Mapped[str] = mapped_column(String(320), nullable=False)
    permissions: Mapped[str] = mapped_column(String(120), default="lookup,read,write,insert,post", nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MailboxPolicy(Base):
    __tablename__ = "mailbox_policies"
    __table_args__ = (UniqueConstraint("mailbox_id", name="uq_mailbox_policy"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True, nullable=False)
    vacation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vacation_subject: Mapped[str | None] = mapped_column(String(240), nullable=True)
    vacation_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    sieve_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MailMigrationJob(Base):
    __tablename__ = "mail_migration_jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True, nullable=False)
    source_provider: Mapped[str] = mapped_column(String(40), nullable=False)
    source_host: Mapped[str] = mapped_column(String(253), nullable=False)
    source_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    source_username: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True, nullable=False)
    folders_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    folders_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    messages_copied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_copied: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MailboxRecoveryJob(Base):
    __tablename__ = "mailbox_recovery_jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True, nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True, nullable=False)
    restored_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReputationSnapshot(Base):
    __tablename__ = "reputation_snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=True)
    domain_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("domains.id", ondelete="CASCADE"), index=True, nullable=True)
    mail_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    ptr_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fcrdns_ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dnsbl_hits_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ResellerAccount(Base):
    __tablename__ = "reseller_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_reseller_tenant"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    discount_bps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_customers: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ResellerCustomer(Base):
    __tablename__ = "reseller_customers"
    __table_args__ = (UniqueConstraint("customer_tenant_id", name="uq_reseller_customer_tenant"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reseller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reseller_accounts.id", ondelete="CASCADE"), index=True, nullable=False)
    customer_tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WhiteLabelBrand(Base):
    __tablename__ = "white_label_brands"
    __table_args__ = (UniqueConstraint("reseller_id", name="uq_white_label_reseller"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reseller_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reseller_accounts.id", ondelete="CASCADE"), index=True, nullable=False)
    brand_name: Mapped[str] = mapped_column(String(120), nullable=False)
    support_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    custom_hostname: Mapped[str | None] = mapped_column(String(253), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DomainOrder(Base):
    __tablename__ = "domain_orders"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    reseller_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reseller_accounts.id", ondelete="SET NULL"), index=True, nullable=True)
    domain_name: Mapped[str] = mapped_column(String(253), index=True, nullable=False)
    operation: Mapped[str] = mapped_column(String(32), default="register", nullable=False)
    years: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), default="opensrs", nullable=False)
    provider_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SmtpCredential(Base):
    __tablename__ = "smtp_credentials"
    __table_args__ = (UniqueConstraint("username", name="uq_smtp_credential_username"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sender_address: Mapped[str | None] = mapped_column(String(320), nullable=True)
    system_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TransactionalMessage(Base):
    __tablename__ = "transactional_messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), index=True, nullable=True)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("smtp_credentials.id", ondelete="SET NULL"), index=True, nullable=True)
    message_id: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    recipients_json: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GroupwareCredential(Base):
    __tablename__ = "groupware_credentials"
    __table_args__ = (UniqueConstraint("mailbox_id", name="uq_groupware_mailbox"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MailNode(Base):
    __tablename__ = "mail_nodes"
    __table_args__ = (UniqueConstraint("name", name="uq_mail_node_name"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    region: Mapped[str] = mapped_column(String(80), default="lesotho", nullable=False)
    public_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
