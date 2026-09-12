"""domain management
Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    domain_status = postgresql.ENUM("pending_verification", "verified", "suspended", "archived", name="domainstatus", create_type=False)
    domain_dns_mode = postgresql.ENUM("external", "platform", name="domaindnsmode", create_type=False)
    postgresql.ENUM("pending_verification", "verified", "suspended", "archived", name="domainstatus").create(bind, checkfirst=True)
    postgresql.ENUM("external", "platform", name="domaindnsmode").create(bind, checkfirst=True)

    op.create_table(
        "domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ascii_name", sa.String(253), nullable=False),
        sa.Column("unicode_name", sa.String(253), nullable=False),
        sa.Column("status", domain_status, nullable=False, server_default="pending_verification"),
        sa.Column("dns_mode", domain_dns_mode, nullable=False, server_default="platform"),
        sa.Column("mail_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("verification_token_hash", sa.String(64), nullable=False),
        sa.Column("verification_token_hint", sa.String(16), nullable=False),
        sa.Column("verification_record_name", sa.String(320), nullable=False),
        sa.Column("ownership_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ascii_name", name="uq_domains_ascii_name"),
    )
    op.create_index("ix_domains_tenant_id", "domains", ["tenant_id"])
    op.create_index("ix_domains_ascii_name", "domains", ["ascii_name"])
    op.create_index("ix_domains_status", "domains", ["status"])

    op.create_table(
        "domain_verification_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("observed_values_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_domain_verification_attempts_domain_id", "domain_verification_attempts", ["domain_id"])

    op.create_table(
        "domain_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_domain_events_domain_id", "domain_events", ["domain_id"])
    op.create_index("ix_domain_events_tenant_id", "domain_events", ["tenant_id"])
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])


def downgrade():
    op.drop_index("ix_domain_events_event_type", table_name="domain_events")
    op.drop_index("ix_domain_events_tenant_id", table_name="domain_events")
    op.drop_index("ix_domain_events_domain_id", table_name="domain_events")
    op.drop_table("domain_events")
    op.drop_index("ix_domain_verification_attempts_domain_id", table_name="domain_verification_attempts")
    op.drop_table("domain_verification_attempts")
    op.drop_index("ix_domains_status", table_name="domains")
    op.drop_index("ix_domains_ascii_name", table_name="domains")
    op.drop_index("ix_domains_tenant_id", table_name="domains")
    op.drop_table("domains")
    bind = op.get_bind()
    postgresql.ENUM(name="domaindnsmode").drop(bind, checkfirst=True)
    postgresql.ENUM(name="domainstatus").drop(bind, checkfirst=True)
