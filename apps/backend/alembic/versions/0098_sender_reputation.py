"""add sender and domain reputation profiles

Revision ID: 0098_sender_reputation
Revises: 0097_trusted_sender
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0098_sender_reputation"
down_revision = "0097_trusted_sender"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sender_reputation_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sender_hash", sa.String(length=64), nullable=False),
        sa.Column("sender_domain", sa.String(length=253), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authenticated_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authentication_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspicious_link_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_legitimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_phishing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_bec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("registry_verified_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "sender_hash", name="uq_sender_reputation_tenant_sender"),
    )
    op.create_index("ix_sender_reputation_profiles_tenant_id", "sender_reputation_profiles", ["tenant_id"])
    op.create_index("ix_sender_reputation_profiles_sender_domain", "sender_reputation_profiles", ["sender_domain"])
    op.create_index("ix_sender_reputation_tenant_score", "sender_reputation_profiles", ["tenant_id", "score"])

    op.create_table(
        "domain_intelligence_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authenticated_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authentication_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspicious_link_messages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_legitimate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_phishing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_bec", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trusted_registry_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("domain_age_days", sa.Integer(), nullable=True),
        sa.Column("identity_status", sa.String(length=40), nullable=False, server_default="unverified"),
        sa.Column("enrichment_source", sa.String(length=80), nullable=True),
        sa.Column("enrichment_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "domain", name="uq_domain_intelligence_tenant_domain"),
    )
    op.create_index("ix_domain_intelligence_profiles_tenant_id", "domain_intelligence_profiles", ["tenant_id"])
    op.create_index("ix_domain_intelligence_tenant_score", "domain_intelligence_profiles", ["tenant_id", "score"])


def downgrade() -> None:
    op.drop_index("ix_domain_intelligence_tenant_score", table_name="domain_intelligence_profiles")
    op.drop_index("ix_domain_intelligence_profiles_tenant_id", table_name="domain_intelligence_profiles")
    op.drop_table("domain_intelligence_profiles")
    op.drop_index("ix_sender_reputation_tenant_score", table_name="sender_reputation_profiles")
    op.drop_index("ix_sender_reputation_profiles_sender_domain", table_name="sender_reputation_profiles")
    op.drop_index("ix_sender_reputation_profiles_tenant_id", table_name="sender_reputation_profiles")
    op.drop_table("sender_reputation_profiles")
