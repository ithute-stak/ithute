"""add MFA recovery audit and account security state

Revision ID: 0003_security_hardening
Revises: 0002_oauth_pkce
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_security_hardening"
down_revision = "0002_oauth_pkce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("security_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_ip", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    op.add_column("auth_sessions", sa.Column("revoked_reason", sa.String(length=160), nullable=True))
    op.add_column("auth_sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    op.create_table(
        "security_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=320), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_security_tokens_user_id", "security_tokens", ["user_id"])
    op.create_index("ix_security_tokens_purpose", "security_tokens", ["purpose"])
    op.create_index("ix_security_tokens_token_hash", "security_tokens", ["token_hash"])
    op.create_index("ix_security_tokens_expires_at", "security_tokens", ["expires_at"])

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_mfa_recovery_user_code"),
    )
    op.create_index("ix_mfa_recovery_codes_user_id", "mfa_recovery_codes", ["user_id"])
    op.create_index("ix_mfa_recovery_codes_code_hash", "mfa_recovery_codes", ["code_hash"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("client_id", sa.String(length=120), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_client_id", "audit_events", ["client_id"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_client_id", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_index("ix_mfa_recovery_codes_code_hash", table_name="mfa_recovery_codes")
    op.drop_index("ix_mfa_recovery_codes_user_id", table_name="mfa_recovery_codes")
    op.drop_table("mfa_recovery_codes")

    op.drop_index("ix_security_tokens_expires_at", table_name="security_tokens")
    op.drop_index("ix_security_tokens_token_hash", table_name="security_tokens")
    op.drop_index("ix_security_tokens_purpose", table_name="security_tokens")
    op.drop_index("ix_security_tokens_user_id", table_name="security_tokens")
    op.drop_table("security_tokens")

    op.drop_column("auth_sessions", "last_seen_at")
    op.drop_column("auth_sessions", "revoked_reason")

    op.drop_column("users", "password_changed_at")
    op.drop_column("users", "last_login_ip")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "security_version")
    op.drop_column("users", "failed_login_attempts")
    op.drop_column("users", "totp_secret_encrypted")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "is_platform_admin")
