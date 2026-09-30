"""add finance expenses, bank reconciliation and service billing links

Revision ID: 0032_finance_accounting_ops
Revises: 0031_finance_documents
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0032_finance_accounting_ops"
down_revision = "0031_finance_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("vendor", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payment_method", sa.String(length=80), server_default="bank_transfer", nullable=False),
        sa.Column("reference", sa.String(length=180), server_default="", nullable=False),
        sa.Column("recurring", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="posted", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="ck_finance_expenses_amount"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_finance_expenses_tax"),
        sa.CheckConstraint("status IN ('posted','void')", name="ck_finance_expenses_status"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["expense_date", "vendor", "category", "reference", "status", "created_by_user_id", "created_at"]:
        op.create_index(f"ix_finance_expenses_{column}", "finance_expenses", [column])

    op.create_table(
        "finance_bank_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("reference", sa.String(length=255), server_default="", nullable=False),
        sa.Column("source_name", sa.String(length=120), server_default="LPB", nullable=False),
        sa.Column("import_batch", sa.String(length=120), server_default="manual", nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="unmatched", nullable=False),
        sa.Column("matched_invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("matched_payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('unmatched','matched','ignored')", name="ck_finance_bank_transactions_status"),
        sa.ForeignKeyConstraint(["matched_invoice_id"], ["finance_invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_payment_id"], ["finance_payments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    for column in ["transaction_date", "reference", "import_batch", "fingerprint", "status", "matched_invoice_id", "matched_payment_id", "created_by_user_id", "created_at"]:
        op.create_index(f"ix_finance_bank_transactions_{column}", "finance_bank_transactions", [column])

    op.create_table(
        "finance_service_billing_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=80), server_default="ithute_product", nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("service_label", sa.String(length=500), nullable=False),
        sa.Column("details", sa.String(length=1200), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rate_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("send_day", sa.Integer(), server_default="1", nullable=False),
        sa.Column("due_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_finance_service_links_quantity"),
        sa.CheckConstraint("rate_minor >= 0", name="ck_finance_service_links_rate"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_finance_service_links_tax"),
        sa.CheckConstraint("send_day >= 1 AND send_day <= 31", name="ck_finance_service_links_send_day"),
        sa.CheckConstraint("due_days >= 0 AND due_days <= 365", name="ck_finance_service_links_due_days"),
        sa.ForeignKeyConstraint(["client_id"], ["finance_clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["finance_invoice_schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "source_type", "source_ref", name="uq_finance_service_link_source"),
    )
    for column in ["client_id", "source_type", "source_ref", "enabled", "schedule_id", "created_by_user_id", "created_at"]:
        op.create_index(f"ix_finance_service_billing_links_{column}", "finance_service_billing_links", [column])


def downgrade() -> None:
    op.drop_table("finance_service_billing_links")
    op.drop_table("finance_bank_transactions")
    op.drop_table("finance_expenses")
