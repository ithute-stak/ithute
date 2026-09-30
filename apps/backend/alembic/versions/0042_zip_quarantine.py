"""add ZIP quarantine metadata

Revision ID: 0042_zip_quarantine
Revises: 0041_hosting_commands
"""

from alembic import op
import sqlalchemy as sa

revision = "0042_zip_quarantine"
down_revision = "0041_hosting_commands"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hosting_sources", sa.Column("upload_token_hash", sa.String(length=64), nullable=True))
    op.add_column("hosting_sources", sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hosting_sources", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hosting_sources", sa.Column("unpacked_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("hosting_sources", sa.Column("file_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("hosting_sources", "file_count")
    op.drop_column("hosting_sources", "unpacked_size_bytes")
    op.drop_column("hosting_sources", "verified_at")
    op.drop_column("hosting_sources", "upload_expires_at")
    op.drop_column("hosting_sources", "upload_token_hash")
