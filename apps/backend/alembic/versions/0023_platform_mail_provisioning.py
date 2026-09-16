"""add platform mail provisioning boundary

Revision ID: 0023_platform_mail_provisioning
Revises: 0022_commercial_catalog
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0023_platform_mail_provisioning"
down_revision = "0022_commercial_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("mailboxes", "created_by_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("mailboxes", sa.Column("created_by_service_client_id", sa.String(length=120), nullable=True))
    op.create_index("ix_mailboxes_created_by_service_client_id", "mailboxes", ["created_by_service_client_id"])

    op.alter_column("mail_aliases", "created_by_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column("mail_aliases", sa.Column("created_by_service_client_id", sa.String(length=120), nullable=True))
    op.create_index("ix_mail_aliases_created_by_service_client_id", "mail_aliases", ["created_by_service_client_id"])

    op.create_table(
        "platform_mail_domain_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_client_id", sa.String(length=120), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allow_create", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_manage", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_client_id", "domain_id", name="uq_platform_mail_client_domain"),
    )
    op.create_index("ix_platform_mail_domain_bindings_service_client_id", "platform_mail_domain_bindings", ["service_client_id"])
    op.create_index("ix_platform_mail_domain_bindings_domain_id", "platform_mail_domain_bindings", ["domain_id"])
    op.create_index("ix_platform_mail_domain_bindings_active", "platform_mail_domain_bindings", ["active"])

    op.create_table(
        "platform_mailbox_provisioning",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_client_id", sa.String(length=120), nullable=False),
        sa.Column("external_reference", sa.String(length=200), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["mailbox_id"], ["mailboxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_client_id", "external_reference", name="uq_platform_mailbox_client_reference"),
        sa.UniqueConstraint("mailbox_id", name="uq_platform_mailbox_provisioning_mailbox"),
    )
    op.create_index("ix_platform_mailbox_provisioning_service_client_id", "platform_mailbox_provisioning", ["service_client_id"])
    op.create_index("ix_platform_mailbox_provisioning_external_reference", "platform_mailbox_provisioning", ["external_reference"])
    op.create_index("ix_platform_mailbox_provisioning_mailbox_id", "platform_mailbox_provisioning", ["mailbox_id"])
    op.create_index("ix_platform_mailbox_provisioning_domain_id", "platform_mailbox_provisioning", ["domain_id"])


def downgrade() -> None:
    op.drop_table("platform_mailbox_provisioning")
    op.drop_table("platform_mail_domain_bindings")
    op.drop_index("ix_mail_aliases_created_by_service_client_id", table_name="mail_aliases")
    op.drop_column("mail_aliases", "created_by_service_client_id")
    op.alter_column("mail_aliases", "created_by_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_index("ix_mailboxes_created_by_service_client_id", table_name="mailboxes")
    op.drop_column("mailboxes", "created_by_service_client_id")
    op.alter_column("mailboxes", "created_by_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
