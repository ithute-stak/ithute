"""add identity devices recovery codes and session risk

Revision ID: 0094_identity_device_risk
Revises: 0093_central_auth_policy
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0094_identity_device_risk"
down_revision = "0093_central_auth_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trusted_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("first_user_agent", sa.String(length=512), nullable=True),
        sa.Column("first_ip_address", sa.String(length=64), nullable=True),
        sa.Column("last_ip_address", sa.String(length=64), nullable=True),
        sa.Column("trusted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "token_hash", name="uq_trusted_device_user_token"),
    )
    op.create_index("ix_trusted_devices_user_id", "trusted_devices", ["user_id"])
    op.create_index("ix_trusted_devices_token_hash", "trusted_devices", ["token_hash"])

    op.create_table(
        "recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_recovery_codes_user_id", "recovery_codes", ["user_id"])
    op.create_index("ix_recovery_codes_code_hash", "recovery_codes", ["code_hash"], unique=True)

    op.add_column("user_sessions", sa.Column("trusted_device_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("user_sessions", sa.Column("risk_score", sa.Integer(), server_default="0", nullable=False))
    op.add_column("user_sessions", sa.Column("risk_level", sa.String(length=20), server_default="low", nullable=False))
    op.add_column("user_sessions", sa.Column("new_device", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("user_sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_user_sessions_trusted_device", "user_sessions", "trusted_devices", ["trusted_device_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_user_sessions_trusted_device_id", "user_sessions", ["trusted_device_id"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_trusted_device_id", table_name="user_sessions")
    op.drop_constraint("fk_user_sessions_trusted_device", "user_sessions", type_="foreignkey")
    op.drop_column("user_sessions", "last_seen_at")
    op.drop_column("user_sessions", "new_device")
    op.drop_column("user_sessions", "risk_level")
    op.drop_column("user_sessions", "risk_score")
    op.drop_column("user_sessions", "trusted_device_id")
    op.drop_index("ix_recovery_codes_code_hash", table_name="recovery_codes")
    op.drop_index("ix_recovery_codes_user_id", table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_index("ix_trusted_devices_token_hash", table_name="trusted_devices")
    op.drop_index("ix_trusted_devices_user_id", table_name="trusted_devices")
    op.drop_table("trusted_devices")
