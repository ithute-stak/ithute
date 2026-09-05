"""Add per-company LoanHub funding provider accounts.

Revision ID: 0005_loanhub_funding_accounts
Revises: 0004_operations_suite
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_loanhub_funding_accounts"
down_revision = "0004_operations_suite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loanhub_funding_provider_configurations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), sa.ForeignKey("merchants.id"), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False, server_default="mpesa"),
        sa.Column("account_reference", sa.String(length=32), nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False, server_default="sandbox"),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="simulator"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("base_url", sa.String(length=255), nullable=False, server_default="https://openapi.m-pesa.com"),
        sa.Column("market", sa.String(length=30), nullable=False, server_default="vodacomLES"),
        sa.Column("country", sa.String(length=3), nullable=False, server_default="LES"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="LSL"),
        sa.Column("service_provider_code", sa.String(length=32), nullable=False),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("public_key", sa.Text(), nullable=True),
        sa.Column("session_activation_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("request_timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.UniqueConstraint("merchant_id","provider","account_reference","environment",name="uq_loanhub_funding_provider_account_environment"),
    )
    for column in ("merchant_id","provider","account_reference","environment","enabled","active"):
        op.create_index(f"ix_loanhub_funding_provider_configurations_{column}","loanhub_funding_provider_configurations",[column])


def downgrade() -> None:
    op.drop_table("loanhub_funding_provider_configurations")
