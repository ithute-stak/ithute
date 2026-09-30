"""add hosting database and source storage metering

Revision ID: 0045_hosting_metering
Revises: 0044_hosting_db_backups
"""

from alembic import op
import sqlalchemy as sa

revision = "0045_hosting_metering"
down_revision = "0044_hosting_db_backups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("billing_plans", sa.Column("hosting_database_limit", sa.Integer(), server_default="0", nullable=False))
    op.add_column("billing_plans", sa.Column("hosting_database_storage_mb", sa.Integer(), server_default="0", nullable=False))
    op.add_column("billing_plans", sa.Column("hosting_source_storage_mb", sa.Integer(), server_default="0", nullable=False))

    op.add_column("usage_snapshots", sa.Column("hosting_database_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("usage_snapshots", sa.Column("hosting_database_storage_bytes", sa.BigInteger(), server_default="0", nullable=False))
    op.add_column("usage_snapshots", sa.Column("hosting_source_storage_bytes", sa.BigInteger(), server_default="0", nullable=False))

    op.execute("UPDATE billing_plans SET hosting_database_limit = CASE WHEN included_hosted_projects > 0 THEN GREATEST(1, included_hosted_projects * 2) ELSE 0 END")
    op.execute("UPDATE billing_plans SET hosting_database_storage_mb = CASE WHEN included_hosted_projects > 0 THEN GREATEST(512, hosting_storage_mb) ELSE 0 END")
    op.execute("UPDATE billing_plans SET hosting_source_storage_mb = CASE WHEN included_hosted_projects > 0 THEN GREATEST(512, hosting_storage_mb) ELSE 0 END")


def downgrade() -> None:
    op.drop_column("usage_snapshots", "hosting_source_storage_bytes")
    op.drop_column("usage_snapshots", "hosting_database_storage_bytes")
    op.drop_column("usage_snapshots", "hosting_database_count")
    op.drop_column("billing_plans", "hosting_source_storage_mb")
    op.drop_column("billing_plans", "hosting_database_storage_mb")
    op.drop_column("billing_plans", "hosting_database_limit")
