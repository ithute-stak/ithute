"""add organisation identity profiles

Revision ID: 0099_org_identity
Revises: 0098_sender_reputation
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0099_org_identity"
down_revision = "0098_sender_reputation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organisation_identity_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(length=160), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=False),
        sa.Column("legitimate_domains_json", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("criticality", sa.String(length=24), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "canonical_name", name="uq_org_identity_tenant_name"),
    )
    op.create_index("ix_org_identity_tenant_active", "organisation_identity_profiles", ["tenant_id", "active"])
    op.create_index("ix_organisation_identity_profiles_tenant_id", "organisation_identity_profiles", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_organisation_identity_profiles_tenant_id", table_name="organisation_identity_profiles")
    op.drop_index("ix_org_identity_tenant_active", table_name="organisation_identity_profiles")
    op.drop_table("organisation_identity_profiles")
