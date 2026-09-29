"""add finance invoices

Revision ID: 0027_finance_invoices
Revises: 0026_mail_forwarding
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0027_finance_invoices"
down_revision = "0026_mail_forwarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=80), nullable=False),
        sa.Column("client_name", sa.String(length=180), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("client_address", sa.String(length=500), server_default="", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("details", sa.String(length=1200), server_default="", nullable=False),
        sa.Column("service_period", sa.String(length=160), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("rate_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="LSL", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("email_subject", sa.String(length=300), nullable=False),
        sa.Column("email_body", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number"),
    )
    op.create_index("ix_finance_invoices_invoice_number", "finance_invoices", ["invoice_number"], unique=True)
    op.create_index("ix_finance_invoices_recipient_email", "finance_invoices", ["recipient_email"], unique=False)
    op.create_index("ix_finance_invoices_status", "finance_invoices", ["status"], unique=False)
    op.create_index("ix_finance_invoices_created_by_user_id", "finance_invoices", ["created_by_user_id"], unique=False)
    op.create_index("ix_finance_invoices_created_at", "finance_invoices", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_finance_invoices_created_at", table_name="finance_invoices")
    op.drop_index("ix_finance_invoices_created_by_user_id", table_name="finance_invoices")
    op.drop_index("ix_finance_invoices_status", table_name="finance_invoices")
    op.drop_index("ix_finance_invoices_recipient_email", table_name="finance_invoices")
    op.drop_index("ix_finance_invoices_invoice_number", table_name="finance_invoices")
    op.drop_table("finance_invoices")
