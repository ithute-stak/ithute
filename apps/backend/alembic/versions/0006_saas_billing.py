"""phase 13 SaaS billing foundation

Revision ID: 0006_saas_billing
Revises: 0005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_saas_billing"
down_revision = "0005"
branch_labels = None
depends_on = None

subscription_status_ddl = postgresql.ENUM(
    "trialing", "active", "past_due", "canceled", name="subscriptionstatus"
)
invoice_status_ddl = postgresql.ENUM(
    "draft", "open", "paid", "void", "uncollectible", name="invoicestatus"
)
subscription_status = postgresql.ENUM(
    "trialing", "active", "past_due", "canceled", name="subscriptionstatus", create_type=False
)
invoice_status = postgresql.ENUM(
    "draft", "open", "paid", "void", "uncollectible", name="invoicestatus", create_type=False
)


def upgrade() -> None:
    # Create PostgreSQL enum types exactly once. The column enum objects use
    # create_type=False so op.create_table() does not attempt to create them a
    # second time via SQLAlchemy's table-level before_create event.
    subscription_status_ddl.create(op.get_bind(), checkfirst=True)
    invoice_status_ddl.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "billing_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="LSL"),
        sa.Column("monthly_price_minor", sa.Integer(), nullable=False),
        sa.Column("included_mailboxes", sa.Integer(), nullable=False),
        sa.Column("included_domains", sa.Integer(), nullable=False),
        sa.Column("included_storage_mb", sa.Integer(), nullable=False),
        sa.Column("max_api_keys", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_billing_plans_code"),
    )
    op.create_index("ix_billing_plans_code", "billing_plans", ["code"], unique=True)

    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("billing_plans.id"), nullable=False),
        sa.Column("status", subscription_status, nullable=False, server_default="trialing"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("provider_customer_id", sa.String(length=120), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscription_tenant"),
    )
    op.create_index("ix_tenant_subscriptions_tenant_id", "tenant_subscriptions", ["tenant_id"])
    op.create_index("ix_tenant_subscriptions_plan_id", "tenant_subscriptions", ["plan_id"])

    op.create_table(
        "usage_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailboxes", sa.Integer(), nullable=False),
        sa.Column("domains", sa.Integer(), nullable=False),
        sa.Column("storage_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_usage_snapshots_tenant_id", "usage_snapshots", ["tenant_id"])
    op.create_index("ix_usage_snapshots_captured_at", "usage_snapshots", ["captured_at"])

    op.create_table(
        "billing_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant_subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_number", sa.String(length=80), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("status", invoice_status, nullable=False, server_default="draft"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("invoice_number", name="uq_billing_invoices_invoice_number"),
    )
    op.create_index("ix_billing_invoices_tenant_id", "billing_invoices", ["tenant_id"])
    op.create_index("ix_billing_invoices_subscription_id", "billing_invoices", ["subscription_id"])
    op.create_index("ix_billing_invoices_invoice_number", "billing_invoices", ["invoice_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_billing_invoices_invoice_number", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_subscription_id", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_tenant_id", table_name="billing_invoices")
    op.drop_table("billing_invoices")
    op.drop_index("ix_usage_snapshots_captured_at", table_name="usage_snapshots")
    op.drop_index("ix_usage_snapshots_tenant_id", table_name="usage_snapshots")
    op.drop_table("usage_snapshots")
    op.drop_index("ix_tenant_subscriptions_plan_id", table_name="tenant_subscriptions")
    op.drop_index("ix_tenant_subscriptions_tenant_id", table_name="tenant_subscriptions")
    op.drop_table("tenant_subscriptions")
    op.drop_index("ix_billing_plans_code", table_name="billing_plans")
    op.drop_table("billing_plans")
    invoice_status_ddl.drop(op.get_bind(), checkfirst=True)
    subscription_status_ddl.drop(op.get_bind(), checkfirst=True)
