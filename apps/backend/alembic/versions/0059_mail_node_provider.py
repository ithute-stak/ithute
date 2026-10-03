"""mail node provider metadata

Revision ID: 0059_mail_node_provider
Revises: 0058_mail_node_operations
"""

from alembic import op
import sqlalchemy as sa

revision = "0059_mail_node_provider"
down_revision = "0058_mail_node_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_nodes", sa.Column("provider", sa.String(80), nullable=True))
    op.add_column("mail_nodes", sa.Column("provider_instance_id", sa.String(180), nullable=True))
    op.create_index("ix_mail_nodes_provider_instance_id", "mail_nodes", ["provider_instance_id"])


def downgrade():
    op.drop_index("ix_mail_nodes_provider_instance_id", table_name="mail_nodes")
    op.drop_column("mail_nodes", "provider_instance_id")
    op.drop_column("mail_nodes", "provider")
