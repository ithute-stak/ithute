"""mailbox management
Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    mailbox_status = postgresql.ENUM("active", "suspended", "archived", name="mailboxstatus", create_type=False)
    postgresql.ENUM("active", "suspended", "archived", name="mailboxstatus").create(bind, checkfirst=True)

    op.create_table(
        "mailboxes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_part", sa.String(64), nullable=False),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False, server_default=str(5 * 1024**3)),
        sa.Column("status", mailbox_status, nullable=False, server_default="active"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("address", name="uq_mailboxes_address"),
        sa.UniqueConstraint("domain_id", "local_part", name="uq_mailboxes_domain_local_part"),
    )
    op.create_index("ix_mailboxes_tenant_id", "mailboxes", ["tenant_id"])
    op.create_index("ix_mailboxes_domain_id", "mailboxes", ["domain_id"])
    op.create_index("ix_mailboxes_address", "mailboxes", ["address"])
    op.create_index("ix_mailboxes_status", "mailboxes", ["status"])

    op.create_table(
        "mail_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_address", sa.String(320), nullable=False),
        sa.Column("destination_address", sa.String(320), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_address", "destination_address", name="uq_mail_alias_route"),
    )
    op.create_index("ix_mail_aliases_tenant_id", "mail_aliases", ["tenant_id"])
    op.create_index("ix_mail_aliases_domain_id", "mail_aliases", ["domain_id"])
    op.create_index("ix_mail_aliases_source_address", "mail_aliases", ["source_address"])

    op.create_table(
        "distribution_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_part", sa.String(64), nullable=False),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("address", name="uq_distribution_groups_address"),
    )
    op.create_index("ix_distribution_groups_tenant_id", "distribution_groups", ["tenant_id"])
    op.create_index("ix_distribution_groups_domain_id", "distribution_groups", ["domain_id"])
    op.create_index("ix_distribution_groups_address", "distribution_groups", ["address"])

    op.create_table(
        "distribution_group_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("distribution_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_address", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("group_id", "destination_address", name="uq_distribution_group_member"),
    )
    op.create_index("ix_distribution_group_members_group_id", "distribution_group_members", ["group_id"])


def downgrade():
    op.drop_index("ix_distribution_group_members_group_id", table_name="distribution_group_members")
    op.drop_table("distribution_group_members")
    op.drop_index("ix_distribution_groups_address", table_name="distribution_groups")
    op.drop_index("ix_distribution_groups_domain_id", table_name="distribution_groups")
    op.drop_index("ix_distribution_groups_tenant_id", table_name="distribution_groups")
    op.drop_table("distribution_groups")
    op.drop_index("ix_mail_aliases_source_address", table_name="mail_aliases")
    op.drop_index("ix_mail_aliases_domain_id", table_name="mail_aliases")
    op.drop_index("ix_mail_aliases_tenant_id", table_name="mail_aliases")
    op.drop_table("mail_aliases")
    op.drop_index("ix_mailboxes_status", table_name="mailboxes")
    op.drop_index("ix_mailboxes_address", table_name="mailboxes")
    op.drop_index("ix_mailboxes_domain_id", table_name="mailboxes")
    op.drop_index("ix_mailboxes_tenant_id", table_name="mailboxes")
    op.drop_table("mailboxes")
    postgresql.ENUM(name="mailboxstatus").drop(op.get_bind(), checkfirst=True)
