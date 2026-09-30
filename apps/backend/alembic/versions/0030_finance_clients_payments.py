"""add finance clients and payment ledger

Revision ID: 0030_finance_clients_payments
Revises: 0029_finance_recurring
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030_finance_clients_payments"
down_revision = "0029_finance_recurring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("address", sa.String(length=500), server_default="", nullable=False),
        sa.Column("phone", sa.String(length=80), server_default="", nullable=False),
        sa.Column("default_service", sa.String(length=500), server_default="", nullable=False),
        sa.Column("default_details", sa.String(length=1200), server_default="", nullable=False),
        sa.Column("default_quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("default_rate_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("default_tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("default_quantity >= 1", name="ck_finance_clients_quantity"),
        sa.CheckConstraint("default_rate_minor >= 0", name="ck_finance_clients_rate"),
        sa.CheckConstraint("default_tax_minor >= 0", name="ck_finance_clients_tax"),
        sa.CheckConstraint("payment_terms_days >= 0 AND payment_terms_days <= 365", name="ck_finance_clients_terms"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_clients_name", "finance_clients", ["name"])
    op.create_index("ix_finance_clients_email", "finance_clients", ["email"])
    op.create_index("ix_finance_clients_active", "finance_clients", ["active"])
    op.create_index("ix_finance_clients_created_by_user_id", "finance_clients", ["created_by_user_id"])
    op.create_index("ix_finance_clients_created_at", "finance_clients", ["created_at"])

    op.add_column("finance_invoices", sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("finance_invoices", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_finance_invoices_client_id_finance_clients",
        "finance_invoices",
        "finance_clients",
        ["client_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_finance_invoices_client_id", "finance_invoices", ["client_id"])

    op.add_column("finance_invoice_schedules", sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_finance_invoice_schedules_client_id_finance_clients",
        "finance_invoice_schedules",
        "finance_clients",
        ["client_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_finance_invoice_schedules_client_id", "finance_invoice_schedules", ["client_id"])

    op.create_table(
        "finance_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=80), server_default="bank_transfer", nullable=False),
        sa.Column("reference", sa.String(length=180), server_default="", nullable=False),
        sa.Column("note", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_finance_payments_amount"),
        sa.ForeignKeyConstraint(["invoice_id"], ["finance_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_payments_invoice_id", "finance_payments", ["invoice_id"])
    op.create_index("ix_finance_payments_payment_date", "finance_payments", ["payment_date"])
    op.create_index("ix_finance_payments_recorded_by_user_id", "finance_payments", ["recorded_by_user_id"])
    op.create_index("ix_finance_payments_created_at", "finance_payments", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_finance_payments_created_at", table_name="finance_payments")
    op.drop_index("ix_finance_payments_recorded_by_user_id", table_name="finance_payments")
    op.drop_index("ix_finance_payments_payment_date", table_name="finance_payments")
    op.drop_index("ix_finance_payments_invoice_id", table_name="finance_payments")
    op.drop_table("finance_payments")

    op.drop_index("ix_finance_invoice_schedules_client_id", table_name="finance_invoice_schedules")
    op.drop_constraint("fk_finance_invoice_schedules_client_id_finance_clients", "finance_invoice_schedules", type_="foreignkey")
    op.drop_column("finance_invoice_schedules", "client_id")

    op.drop_index("ix_finance_invoices_client_id", table_name="finance_invoices")
    op.drop_constraint("fk_finance_invoices_client_id_finance_clients", "finance_invoices", type_="foreignkey")
    op.drop_column("finance_invoices", "cancelled_at")
    op.drop_column("finance_invoices", "client_id")

    op.drop_index("ix_finance_clients_created_at", table_name="finance_clients")
    op.drop_index("ix_finance_clients_created_by_user_id", table_name="finance_clients")
    op.drop_index("ix_finance_clients_active", table_name="finance_clients")
    op.drop_index("ix_finance_clients_email", table_name="finance_clients")
    op.drop_index("ix_finance_clients_name", table_name="finance_clients")
    op.drop_table("finance_clients")
