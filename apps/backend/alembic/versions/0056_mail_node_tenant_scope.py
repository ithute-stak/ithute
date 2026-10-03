"""mail node tenant scope

Revision ID: 0056_mail_node_tenant_scope
Revises: 0055_mail_node_agent
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0056_mail_node_tenant_scope"
down_revision = "0055_mail_node_agent"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_nodes",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_mail_nodes_tenant_id", "mail_nodes", ["tenant_id"])


def downgrade():
    op.drop_index("ix_mail_nodes_tenant_id", table_name="mail_nodes")
    op.drop_column("mail_nodes", "tenant_id")
