"""add finance sender configuration

Revision ID: 0028_finance_sender_configuration
Revises: 0027_finance_invoices
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0028_finance_sender_configuration"
down_revision = "0027_finance_invoices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_sender_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sender_email", sa.String(length=320), nullable=False),
        sa.Column("smtp_username", sa.String(length=320), nullable=False),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("security_mode", sa.String(length=20), server_default="starttls", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verification_error", sa.String(length=1000), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("finance_sender_configurations")
