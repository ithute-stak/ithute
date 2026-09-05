"""add WebAuthn passkeys

Revision ID: 0004_webauthn_passkeys
Revises: 0003_security_hardening
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_webauthn_passkeys"
down_revision = "0003_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("credential_id", sa.String(length=1024), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("device_type", sa.String(length=80), nullable=True),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("transports_json", sa.Text(), nullable=True),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index("ix_passkey_credentials_user_id", "passkey_credentials", ["user_id"])
    op.create_index("ix_passkey_credentials_credential_id", "passkey_credentials", ["credential_id"])

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("challenge", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge"),
    )
    op.create_index("ix_webauthn_challenges_user_id", "webauthn_challenges", ["user_id"])
    op.create_index("ix_webauthn_challenges_purpose", "webauthn_challenges", ["purpose"])
    op.create_index("ix_webauthn_challenges_challenge", "webauthn_challenges", ["challenge"])
    op.create_index("ix_webauthn_challenges_expires_at", "webauthn_challenges", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_webauthn_challenges_expires_at", table_name="webauthn_challenges")
    op.drop_index("ix_webauthn_challenges_challenge", table_name="webauthn_challenges")
    op.drop_index("ix_webauthn_challenges_purpose", table_name="webauthn_challenges")
    op.drop_index("ix_webauthn_challenges_user_id", table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")

    op.drop_index("ix_passkey_credentials_credential_id", table_name="passkey_credentials")
    op.drop_index("ix_passkey_credentials_user_id", table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
