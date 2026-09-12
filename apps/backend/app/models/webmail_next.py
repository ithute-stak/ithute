from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ConnectedMailAccount(Base):
    __tablename__ = "connected_mail_accounts"
    __table_args__ = (
        UniqueConstraint("mailbox_id", "address", name="uq_connected_mail_account_mailbox_address"),
        Index("ix_connected_mail_account_mailbox_status", "mailbox_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="custom")
    address: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="password")

    # Passwords/app-passwords are only persisted after explicit opt-in. OAuth
    # refresh/access tokens are protected with the same application encryption
    # primitive used for other Webmail secrets and are never returned by APIs.
    credential_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    oauth_scopes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    imap_host: Mapped[str] = mapped_column(String(253), nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, nullable=False, default=993)
    imap_security: Mapped[str] = mapped_column(String(20), nullable=False, default="ssl")
    smtp_host: Mapped[str] = mapped_column(String(253), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_security: Mapped[str] = mapped_column(String(20), nullable=False, default="starttls")

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MailSnooze(Base):
    __tablename__ = "mail_snoozes"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_id", "source_key", "folder", "message_uid", name="uq_mail_snooze_source_message"
        ),
        Index("ix_mail_snooze_mailbox_wake", "mailbox_id", "wake_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connected_mail_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_key: Mapped[str] = mapped_column(String(80), nullable=False, default="hosted")
    folder: Mapped[str] = mapped_column(String(255), nullable=False, default="INBOX")
    message_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    message_id: Mapped[str | None] = mapped_column(String(998), nullable=True)
    wake_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ScheduledMail(Base):
    __tablename__ = "scheduled_mail"
    __table_args__ = (
        Index("ix_scheduled_mail_due", "status", "scheduled_at"),
        Index("ix_scheduled_mail_mailbox_created", "mailbox_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connected_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("connected_mail_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_key: Mapped[str] = mapped_column(String(80), nullable=False, default="hosted")
    to_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cc_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    bcc_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(String(998), nullable=False, default="")
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attachments_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Hosted-mail scheduled sends need a transient encrypted mailbox secret so
    # delivery can continue after the browser session closes. It is erased as
    # soon as the job is sent, cancelled or permanently fails.
    auth_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
