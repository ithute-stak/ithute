"""add zero trust session assurance and device trust

Revision ID: 0010_zero_trust_sessions
Revises: 0009_bda_mail_forward
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_zero_trust_sessions"
down_revision = "0009_bda_mail_forward"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("assurance_level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("auth_sessions", sa.Column("auth_method", sa.String(length=80), nullable=False, server_default="password"))
    op.add_column("auth_sessions", sa.Column("last_step_up_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("auth_sessions", sa.Column("risk_level", sa.String(length=16), nullable=False, server_default="low"))
    op.add_column("auth_sessions", sa.Column("risk_reasons_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("devices", sa.Column("trusted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("devices", sa.Column("last_ip_address", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "last_ip_address")
    op.drop_column("devices", "trusted_at")
    op.drop_column("auth_sessions", "risk_reasons_json")
    op.drop_column("auth_sessions", "risk_level")
    op.drop_column("auth_sessions", "last_step_up_at")
    op.drop_column("auth_sessions", "auth_method")
    op.drop_column("auth_sessions", "assurance_level")
