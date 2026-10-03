"""mail backup immutability windows

Revision ID: 0062_mail_backup_immutability
Revises: 0061_domain_health_monitor
"""

from alembic import op
import sqlalchemy as sa

revision = "0062_mail_backup_immutability"
down_revision = "0061_domain_health_monitor"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mail_nodes",
        sa.Column("backup_immutability_days", sa.Integer(), nullable=False, server_default="7"),
    )
    op.add_column(
        "mail_node_snapshots",
        sa.Column("immutable_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("mail_node_snapshots", "immutable_until")
    op.drop_column("mail_nodes", "backup_immutability_days")
