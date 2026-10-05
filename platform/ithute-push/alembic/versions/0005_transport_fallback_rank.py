"""add push transport fallback rank

Revision ID: 0005_transport_fallback_rank
Revises: 0004_multi_transport_endpoints
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_transport_fallback_rank"
down_revision = "0004_multi_transport_endpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "deliveries",
        sa.Column("transport_rank", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("deliveries", "transport_rank")
