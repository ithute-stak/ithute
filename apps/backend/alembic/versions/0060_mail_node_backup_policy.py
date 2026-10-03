"""mail node backup readiness policy

Revision ID: 0060_mail_node_backup_policy
Revises: 0059_mail_node_provider
"""

from alembic import op
import sqlalchemy as sa

revision = "0060_mail_node_backup_policy"
down_revision = "0059_mail_node_provider"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_nodes", sa.Column("backup_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mail_nodes", sa.Column("backup_error", sa.Text(), nullable=True))
    op.add_column("mail_nodes", sa.Column("backup_interval_hours", sa.Integer(), nullable=False, server_default="24"))
    op.add_column("mail_nodes", sa.Column("backup_retention_count", sa.Integer(), nullable=False, server_default="7"))


def downgrade():
    op.drop_column("mail_nodes", "backup_retention_count")
    op.drop_column("mail_nodes", "backup_interval_hours")
    op.drop_column("mail_nodes", "backup_error")
    op.drop_column("mail_nodes", "backup_ready")
