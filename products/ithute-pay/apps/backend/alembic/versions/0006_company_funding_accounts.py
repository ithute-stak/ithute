"""Add segregated LoanHub company funding accounts.

Revision ID: 0006_company_funding_accounts
Revises: 0005_loanhub_funding_accounts
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_company_funding_accounts"
down_revision = "0005_loanhub_funding_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merchant_funding_accounts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("merchant_id", sa.String(length=36), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("application_id", sa.String(length=36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("account_reference", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False, server_default="mpesa"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="LSL"),
        sa.Column("settlement_destination_type", sa.String(length=40), nullable=False, server_default="business_shortcode"),
        sa.Column("settlement_destination_reference", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.UniqueConstraint("merchant_id","application_id","account_reference","currency",name="uq_merchant_funding_account_reference"),
    )
    op.create_table(
        "funding_ledger_entries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("funding_account_id", sa.String(length=36), sa.ForeignKey("merchant_funding_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("application_id", sa.String(length=36), sa.ForeignKey("applications.id"), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(18,2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="LSL"),
        sa.Column("entry_type", sa.String(length=50), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False, unique=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table, columns in {
        "merchant_funding_accounts":["public_id","merchant_id","application_id","account_reference","provider","currency","enabled","status"],
        "funding_ledger_entries":["funding_account_id","merchant_id","application_id","direction","currency","entry_type","resource_type","resource_id","idempotency_key"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}",table,[column])


def downgrade() -> None:
    op.drop_table("funding_ledger_entries")
    op.drop_table("merchant_funding_accounts")
