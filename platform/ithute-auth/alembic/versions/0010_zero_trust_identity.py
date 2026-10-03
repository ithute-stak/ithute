"""zero trust identity hardening

Revision ID: 0010_zero_trust_identity
Revises: 0009_bda_mail_forward_grant
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_zero_trust_identity"
down_revision = "0009_bda_mail_forward_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("trusted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("first_seen_ip", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("last_seen_ip", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("user_agent_hash", sa.String(length=64), nullable=True))
    op.add_column("devices", sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("auth_sessions", sa.Column("auth_method", sa.String(length=32), nullable=False, server_default="password"))
    op.add_column("auth_sessions", sa.Column("risk_score", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("auth_sessions", sa.Column("risk_reasons_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("auth_sessions", sa.Column("step_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auth_sessions", sa.Column("device_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_auth_sessions_device_id_devices", "auth_sessions", "devices", ["device_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_auth_sessions_device_id", "auth_sessions", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_device_id", table_name="auth_sessions")
    op.drop_constraint("fk_auth_sessions_device_id_devices", "auth_sessions", type_="foreignkey")
    op.drop_column("auth_sessions", "device_id")
    op.drop_column("auth_sessions", "step_up_at")
    op.drop_column("auth_sessions", "risk_reasons_json")
    op.drop_column("auth_sessions", "risk_score")
    op.drop_column("auth_sessions", "auth_method")

    op.drop_column("devices", "risk_score")
    op.drop_column("devices", "user_agent_hash")
    op.drop_column("devices", "last_seen_ip")
    op.drop_column("devices", "first_seen_ip")
    op.drop_column("devices", "revoked_at")
    op.drop_column("devices", "trusted_at")
