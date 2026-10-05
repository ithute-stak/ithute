"""add PostgreSQL replica WAL telemetry

Revision ID: 0087_pg_wal_telemetry
Revises: 0086_external_fencing
"""

from alembic import op
import sqlalchemy as sa

revision = "0087_pg_wal_telemetry"
down_revision = "0086_external_fencing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_database_replicas", sa.Column("receive_lsn", sa.String(length=64), nullable=True))
    op.add_column("hosting_database_replicas", sa.Column("replay_lsn", sa.String(length=64), nullable=True))
    op.add_column("hosting_database_replicas", sa.Column("in_recovery", sa.Boolean(), nullable=True))
    op.add_column("hosting_database_replicas", sa.Column("telemetry_error", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("hosting_database_replicas", "telemetry_error")
    op.drop_column("hosting_database_replicas", "in_recovery")
    op.drop_column("hosting_database_replicas", "replay_lsn")
    op.drop_column("hosting_database_replicas", "receive_lsn")
