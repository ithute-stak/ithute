"""add tenant trusted sender profiles

Revision ID: 0097_trusted_sender
Revises: 0096_mail_identity_idx
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0097_trusted_sender"
down_revision = "0096_mail_identity_idx"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trusted_sender_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("sender_addresses_json", sa.JSON(), nullable=False),
        sa.Column("sender_domains_json", sa.JSON(), nullable=False),
        sa.Column("allowed_link_domains_json", sa.JSON(), nullable=False),
        sa.Column("require_spf", sa.Boolean(), nullable=False),
        sa.Column("require_dkim", sa.Boolean(), nullable=False),
        sa.Column("require_dmarc", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_trusted_sender_tenant_name"),
    )
    op.create_index("ix_trusted_sender_tenant_active", "trusted_sender_profiles", ["tenant_id", "active"])
    op.create_index(op.f("ix_trusted_sender_profiles_tenant_id"), "trusted_sender_profiles", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_trusted_sender_profiles_tenant_id"), table_name="trusted_sender_profiles")
    op.drop_index("ix_trusted_sender_tenant_active", table_name="trusted_sender_profiles")
    op.drop_table("trusted_sender_profiles")
