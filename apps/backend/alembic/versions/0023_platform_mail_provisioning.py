"""add platform mail provisioning

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
    op.create_table(
        "platform_mail_domain_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_client_id", sa.String(length=120), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("service_client_id", "domain_id", name="uq_platform_mail_grant_client_domain"),
    )
    op.create_index(
        "ix_platform_mail_domain_grants_service_client_id",
        "platform_mail_domain_grants",
        ["service_client_id"],
    )
    op.create_index("ix_platform_mail_domain_grants_domain_id", "platform_mail_domain_grants", ["domain_id"])
    op.create_index("ix_platform_mail_domain_grants_active", "platform_mail_domain_grants", ["active"])

    op.create_table(
        "platform_mailbox_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_client_id", sa.String(length=120), nullable=False),
        sa.Column("external_reference", sa.String(length=200), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain_grant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["mailbox_id"], ["mailboxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["domain_grant_id"], ["platform_mail_domain_grants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_client_id",
            "external_reference",
            name="uq_platform_mailbox_binding_client_reference",
        ),
        sa.UniqueConstraint("mailbox_id", name="uq_platform_mailbox_binding_mailbox"),
    )
    op.create_index(
        "ix_platform_mailbox_bindings_service_client_id",
        "platform_mailbox_bindings",
        ["service_client_id"],
    )
    op.create_index(
        "ix_platform_mailbox_bindings_external_reference",
        "platform_mailbox_bindings",
        ["external_reference"],
    )
    op.create_index("ix_platform_mailbox_bindings_mailbox_id", "platform_mailbox_bindings", ["mailbox_id"])
    op.create_index(
        "ix_platform_mailbox_bindings_domain_grant_id",
        "platform_mailbox_bindings",
        ["domain_grant_id"],
    )


def downgrade() -> None:
    op.drop_table("platform_mailbox_bindings")
    op.drop_table("platform_mail_domain_grants")
