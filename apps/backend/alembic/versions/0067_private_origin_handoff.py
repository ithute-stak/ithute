"""add trusted hosting origin handoff

Revision ID: 0067_private_origin_handoff
Revises: 0066_hosting_provisioning
"""

from alembic import op
import sqlalchemy as sa

revision = "0067_private_origin_handoff"
down_revision = "0066_hosting_provisioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_deployments", sa.Column("origin_url", sa.String(length=1000), nullable=True))
    op.add_column("hosting_deployments", sa.Column("origin_reported_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("hosting_deployments", "origin_reported_at")
    op.drop_column("hosting_deployments", "origin_url")
