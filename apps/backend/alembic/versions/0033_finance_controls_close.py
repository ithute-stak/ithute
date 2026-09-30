"""add finance period locks, tax rates and refunds

Revision ID: 0033_finance_controls_close
Revises: 0032_finance_accounting_ops
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0033_finance_controls_close"
down_revision = "0032_finance_accounting_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_accounting_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("note", sa.Text(), server_default="", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("year >= 2000 AND year <= 2100", name="ck_finance_accounting_period_year"),
        sa.CheckConstraint("month >= 1 AND month <= 12", name="ck_finance_accounting_period_month"),
        sa.CheckConstraint("status IN ('open','locked')", name="ck_finance_accounting_period_status"),
        sa.ForeignKeyConstraint(["locked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("year", "month", name="uq_finance_accounting_period"),
    )
    op.create_index("ix_finance_accounting_periods_year", "finance_accounting_periods", ["year"])
    op.create_index("ix_finance_accounting_periods_month", "finance_accounting_periods", ["month"])
    op.create_index("ix_finance_accounting_periods_status", "finance_accounting_periods", ["status"])
    op.create_index("ix_finance_accounting_periods_locked_by_user_id", "finance_accounting_periods", ["locked_by_user_id"])

    op.create_table(
        "finance_tax_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("rate_basis_points", sa.Integer(), nullable=False),
        sa.Column("inclusive", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rate_basis_points >= 0 AND rate_basis_points <= 10000", name="ck_finance_tax_rate_bps"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_finance_tax_rates_name", "finance_tax_rates", ["name"])
    op.create_index("ix_finance_tax_rates_active", "finance_tax_rates", ["active"])
    op.create_index("ix_finance_tax_rates_created_by_user_id", "finance_tax_rates", ["created_by_user_id"])

    op.create_table(
        "finance_refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("refund_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=80), server_default="bank_transfer", nullable=False),
        sa.Column("reference", sa.String(length=180), server_default="", nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="processed", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_finance_refunds_amount"),
        sa.CheckConstraint("status IN ('processed')", name="ck_finance_refunds_status"),
        sa.ForeignKeyConstraint(["invoice_id"], ["finance_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payment_id"], ["finance_payments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["invoice_id", "payment_id", "refund_date", "reference", "status", "created_by_user_id"]:
        op.create_index(f"ix_finance_refunds_{column}", "finance_refunds", [column])


def downgrade() -> None:
    op.drop_table("finance_refunds")
    op.drop_table("finance_tax_rates")
    op.drop_table("finance_accounting_periods")
