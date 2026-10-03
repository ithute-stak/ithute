"""dual control approvals for catastrophic operations

Revision ID: 0064_security_approvals
Revises: 0063_audit_integrity
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0064_security_approvals"
down_revision = "0063_audit_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("action", sa.String(length=120), nullable=False, index=True),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=160), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending", index=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_security_approval_resource",
        "security_approval_requests",
        ["action", "resource_type", "resource_id"],
    )


def downgrade():
    op.drop_index("ix_security_approval_resource", table_name="security_approval_requests")
    op.drop_table("security_approval_requests")
