"""security change approvals

Revision ID: 0062_security_approvals
Revises: 0061_domain_health_monitor
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0062_security_approvals"
down_revision = "0061_domain_health_monitor"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(160), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_security_approval_requests_status", "security_approval_requests", ["status"])
    op.create_index("ix_security_approval_requests_action", "security_approval_requests", ["action"])
    op.create_index("ix_security_approval_requests_requested_by", "security_approval_requests", ["requested_by_user_id"])


def downgrade():
    op.drop_index("ix_security_approval_requests_requested_by", table_name="security_approval_requests")
    op.drop_index("ix_security_approval_requests_action", table_name="security_approval_requests")
    op.drop_index("ix_security_approval_requests_status", table_name="security_approval_requests")
    op.drop_table("security_approval_requests")
