"""mailbox storage location

Revision ID: 0053_mailbox_storage_location
Revises: 0052_catalog_lifecycle
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0053_mailbox_storage_location"
down_revision = "0052_catalog_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    storage_type = postgresql.ENUM("internal", "external", name="mailboxstoragetype", create_type=False)
    postgresql.ENUM("internal", "external", name="mailboxstoragetype").create(bind, checkfirst=True)

    op.add_column(
        "mailboxes",
        sa.Column("storage_type", storage_type, nullable=False, server_default="internal"),
    )
    op.add_column(
        "mailboxes",
        sa.Column(
            "mail_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mail_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("mailboxes", sa.Column("storage_path", sa.String(500), nullable=True))
    op.create_index("ix_mailboxes_storage_type", "mailboxes", ["storage_type"])
    op.create_index("ix_mailboxes_mail_node_id", "mailboxes", ["mail_node_id"])


def downgrade():
    op.drop_index("ix_mailboxes_mail_node_id", table_name="mailboxes")
    op.drop_index("ix_mailboxes_storage_type", table_name="mailboxes")
    op.drop_column("mailboxes", "storage_path")
    op.drop_column("mailboxes", "mail_node_id")
    op.drop_column("mailboxes", "storage_type")
    postgresql.ENUM(name="mailboxstoragetype").drop(op.get_bind(), checkfirst=True)
