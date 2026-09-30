"""add hosted project build and start commands

Revision ID: 0041_hosting_commands
Revises: 0040_hosting_builds
"""

from alembic import op
import sqlalchemy as sa

revision = "0041_hosting_commands"
down_revision = "0040_hosting_builds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_projects", sa.Column("build_command", sa.String(length=1000), nullable=True))
    op.add_column("hosting_projects", sa.Column("start_command", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("hosting_projects", "start_command")
    op.drop_column("hosting_projects", "build_command")
