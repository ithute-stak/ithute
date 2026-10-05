"""add metered commercial overages

Revision ID: 0074_metered_overages
Revises: 0073_infrastructure_security
"""

from alembic import op
import sqlalchemy as sa

revision = "0074_metered_overages"
down_revision = "0073_infrastructure_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in (
        "overage_mailbox_minor",
        "overage_domain_minor",
        "overage_storage_gb_minor",
        "overage_api_key_minor",
        "overage_hosted_project_minor",
        "overage_hosting_storage_gb_minor",
        "overage_database_minor",
        "overage_database_storage_gb_minor",
        "overage_source_storage_gb_minor",
    ):
        op.add_column("billing_plans", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_plans", sa.Column("allow_metered_overages", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column("usage_snapshots", sa.Column("api_keys", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("usage_snapshots", sa.Column("hosted_projects", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("usage_snapshots", sa.Column("hosting_storage_bytes", sa.BigInteger(), nullable=False, server_default="0"))

    op.add_column("billing_invoices", sa.Column("base_amount_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_invoices", sa.Column("overage_amount_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_invoices", sa.Column("usage_breakdown_json", sa.Text(), nullable=False, server_default="{}"))
    op.execute("UPDATE billing_invoices SET base_amount_minor = subtotal_minor WHERE base_amount_minor = 0")


def downgrade() -> None:
    op.drop_column("billing_invoices", "usage_breakdown_json")
    op.drop_column("billing_invoices", "overage_amount_minor")
    op.drop_column("billing_invoices", "base_amount_minor")

    op.drop_column("usage_snapshots", "hosting_storage_bytes")
    op.drop_column("usage_snapshots", "hosted_projects")
    op.drop_column("usage_snapshots", "api_keys")

    op.drop_column("billing_plans", "allow_metered_overages")
    for name in (
        "overage_source_storage_gb_minor",
        "overage_database_storage_gb_minor",
        "overage_database_minor",
        "overage_hosting_storage_gb_minor",
        "overage_hosted_project_minor",
        "overage_api_key_minor",
        "overage_storage_gb_minor",
        "overage_domain_minor",
        "overage_mailbox_minor",
    ):
        op.drop_column("billing_plans", name)
