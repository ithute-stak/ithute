"""platform self-domain lifecycle

Revision ID: 0010_platform_self_domain
Revises: 0009_professional_hosting
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_platform_self_domain"
down_revision = "0009_professional_hosting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_configuration",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="bootstrap"),
        sa.Column("security_level", sa.String(length=32), nullable=False, server_default="bootstrap"),
        sa.Column("bootstrap_public_ip", sa.String(length=64), nullable=True),
        sa.Column("primary_domain", sa.String(length=253), nullable=True),
        sa.Column("panel_hostname", sa.String(length=253), nullable=True),
        sa.Column("api_hostname", sa.String(length=253), nullable=True),
        sa.Column("groupware_hostname", sa.String(length=253), nullable=True),
        sa.Column("mail_hostname", sa.String(length=253), nullable=True),
        sa.Column("nameserver_1", sa.String(length=253), nullable=True),
        sa.Column("nameserver_2", sa.String(length=253), nullable=True),
        sa.Column("nameserver_1_ip", sa.String(length=64), nullable=True),
        sa.Column("nameserver_2_ip", sa.String(length=64), nullable=True),
        sa.Column("acme_email", sa.String(length=320), nullable=True),
        sa.Column("dns_zone_provisioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delegation_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("primary_domain", name="uq_platform_configuration_primary_domain"),
    )


def downgrade() -> None:
    op.drop_table("platform_configuration")
