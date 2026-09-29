"""add recurring finance invoice schedules

Revision ID: 0029_finance_recurring
Revises: 0028_finance_sender
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0029_finance_recurring"
down_revision = "0028_finance_sender"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_invoice_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_name", sa.String(length=180), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("client_address", sa.String(length=500), server_default="", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("details", sa.String(length=1200), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rate_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="LSL", nullable=False),
        sa.Column("send_day", sa.Integer(), nullable=False),
        sa.Column("due_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_sent_period", sa.String(length=7), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("send_day >= 1 AND send_day <= 31", name="ck_finance_schedule_send_day"),
        sa.CheckConstraint("due_days >= 0 AND due_days <= 365", name="ck_finance_schedule_due_days"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_invoice_schedules_recipient_email", "finance_invoice_schedules", ["recipient_email"])
    op.create_index("ix_finance_invoice_schedules_enabled", "finance_invoice_schedules", ["enabled"])
    op.create_index("ix_finance_invoice_schedules_created_by_user_id", "finance_invoice_schedules", ["created_by_user_id"])
    op.create_index("ix_finance_invoice_schedules_created_at", "finance_invoice_schedules", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_finance_invoice_schedules_created_at", table_name="finance_invoice_schedules")
    op.drop_index("ix_finance_invoice_schedules_created_by_user_id", table_name="finance_invoice_schedules")
    op.drop_index("ix_finance_invoice_schedules_enabled", table_name="finance_invoice_schedules")
    op.drop_index("ix_finance_invoice_schedules_recipient_email", table_name="finance_invoice_schedules")
    op.drop_table("finance_invoice_schedules")
