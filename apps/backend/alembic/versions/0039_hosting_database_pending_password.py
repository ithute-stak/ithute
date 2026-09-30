"""stage hosting database password rotations safely

Revision ID: 0039_hosting_database_pending_password
Revises: 0038_hosting_git_credentials
"""

from alembic import op
import sqlalchemy as sa

revision = "0039_hosting_database_pending_password"
down_revision = "0038_hosting_git_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_databases", sa.Column("pending_encrypted_password", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("hosting_databases", "pending_encrypted_password")
