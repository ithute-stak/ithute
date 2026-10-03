"""mail node infrastructure metadata

Revision ID: 0054_mail_node_infrastructure
Revises: 0053_mailbox_storage_location
"""

from alembic import op
import sqlalchemy as sa

revision = "0054_mail_node_infrastructure"
down_revision = "0053_mailbox_storage_location"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_nodes", sa.Column("ssh_port", sa.Integer(), nullable=False, server_default="22"))
    op.add_column("mail_nodes", sa.Column("ssh_user", sa.String(80), nullable=True))
    op.add_column("mail_nodes", sa.Column("storage_path", sa.String(500), nullable=False, server_default="/srv/ithute-mail"))
    op.add_column("mail_nodes", sa.Column("capabilities_json", sa.Text(), nullable=False, server_default='["mail","storage"]'))
    op.add_column("mail_nodes", sa.Column("total_storage_bytes", sa.BigInteger(), nullable=True))
    op.add_column("mail_nodes", sa.Column("used_storage_bytes", sa.BigInteger(), nullable=True))
    op.add_column("mail_nodes", sa.Column("agent_version", sa.String(80), nullable=True))


def downgrade():
    op.drop_column("mail_nodes", "agent_version")
    op.drop_column("mail_nodes", "used_storage_bytes")
    op.drop_column("mail_nodes", "total_storage_bytes")
    op.drop_column("mail_nodes", "capabilities_json")
    op.drop_column("mail_nodes", "storage_path")
    op.drop_column("mail_nodes", "ssh_user")
    op.drop_column("mail_nodes", "ssh_port")
