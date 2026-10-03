"""mail node readiness

Revision ID: 0057_mail_node_readiness
Revises: 0056_mail_node_tenant_scope
"""

from alembic import op
import sqlalchemy as sa

revision = "0057_mail_node_readiness"
down_revision = "0056_mail_node_tenant_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_nodes", sa.Column("smtp_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mail_nodes", sa.Column("imap_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mail_nodes", sa.Column("tls_ready", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("mail_nodes", sa.Column("tls_not_after", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mail_nodes", sa.Column("readiness_error", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("mail_nodes", "readiness_error")
    op.drop_column("mail_nodes", "tls_not_after")
    op.drop_column("mail_nodes", "tls_ready")
    op.drop_column("mail_nodes", "imap_ready")
    op.drop_column("mail_nodes", "smtp_ready")
