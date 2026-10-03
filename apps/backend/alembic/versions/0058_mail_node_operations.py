"""mail node operations and snapshots

Revision ID: 0058_mail_node_operations
Revises: 0057_mail_node_readiness
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0058_mail_node_operations"
down_revision = "0057_mail_node_readiness"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "mail_node_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mail_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mail_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mail_node_operations_node_id", "mail_node_operations", ["node_id"])
    op.create_index("ix_mail_node_operations_target_node_id", "mail_node_operations", ["target_node_id"])
    op.create_index("ix_mail_node_operations_tenant_id", "mail_node_operations", ["tenant_id"])
    op.create_index("ix_mail_node_operations_status", "mail_node_operations", ["status"])

    op.create_table(
        "mail_node_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mail_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot_key", sa.String(180), nullable=False, unique=True),
        sa.Column("remote_uri", sa.String(1000), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="creating"),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mail_node_snapshots_node_id", "mail_node_snapshots", ["node_id"])
    op.create_index("ix_mail_node_snapshots_tenant_id", "mail_node_snapshots", ["tenant_id"])
    op.create_index("ix_mail_node_snapshots_status", "mail_node_snapshots", ["status"])


def downgrade():
    op.drop_index("ix_mail_node_snapshots_status", table_name="mail_node_snapshots")
    op.drop_index("ix_mail_node_snapshots_tenant_id", table_name="mail_node_snapshots")
    op.drop_index("ix_mail_node_snapshots_node_id", table_name="mail_node_snapshots")
    op.drop_table("mail_node_snapshots")
    op.drop_index("ix_mail_node_operations_status", table_name="mail_node_operations")
    op.drop_index("ix_mail_node_operations_tenant_id", table_name="mail_node_operations")
    op.drop_index("ix_mail_node_operations_target_node_id", table_name="mail_node_operations")
    op.drop_index("ix_mail_node_operations_node_id", table_name="mail_node_operations")
    op.drop_table("mail_node_operations")
