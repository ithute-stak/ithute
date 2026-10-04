"""add unified infrastructure server registry

Revision ID: 0061_infrastructure_servers
Revises: 0060_mail_node_backup_policy
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0061_infrastructure_servers"
down_revision = "0060_mail_node_backup_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("public_ip", sa.String(length=64), nullable=True),
        sa.Column("region", sa.String(length=80), nullable=False, server_default="lesotho"),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("roles_json", sa.Text(), nullable=False, server_default='["application"]'),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("mail_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mail_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("hosting_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("hostname", name="uq_infrastructure_server_hostname"),
        sa.UniqueConstraint("mail_node_id", name="uq_infrastructure_server_mail_node"),
        sa.UniqueConstraint("hosting_node_id", name="uq_infrastructure_server_hosting_node"),
    )
    op.create_index("ix_infrastructure_servers_hostname", "infrastructure_servers", ["hostname"])
    op.create_index("ix_infrastructure_servers_status", "infrastructure_servers", ["status"])
    op.create_index("ix_infrastructure_servers_mail_node_id", "infrastructure_servers", ["mail_node_id"])
    op.create_index("ix_infrastructure_servers_hosting_node_id", "infrastructure_servers", ["hosting_node_id"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_servers_hosting_node_id", table_name="infrastructure_servers")
    op.drop_index("ix_infrastructure_servers_mail_node_id", table_name="infrastructure_servers")
    op.drop_index("ix_infrastructure_servers_status", table_name="infrastructure_servers")
    op.drop_index("ix_infrastructure_servers_hostname", table_name="infrastructure_servers")
    op.drop_table("infrastructure_servers")
