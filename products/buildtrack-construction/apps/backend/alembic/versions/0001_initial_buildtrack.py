"""initial BuildTrack company foundation

Revision ID: 0001_initial_buildtrack
Revises:
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_buildtrack"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=80), nullable=False, server_default="Lesotho"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="LSL"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("companies")
