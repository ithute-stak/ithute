"""phase 13 billing operations

Revision ID: 0007_billing_operations
Revises: 0006_saas_billing
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_billing_operations"
down_revision = "0006_saas_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_subscriptions", sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenant_subscriptions", sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("usage_snapshots", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("usage_snapshots", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))

    op.add_column("billing_invoices", sa.Column("usage_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("billing_invoices", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_invoices", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("billing_invoices", sa.Column("provider_invoice_id", sa.String(length=160), nullable=True))
    op.add_column("billing_invoices", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_billing_invoices_usage_snapshot_id",
        "billing_invoices",
        "usage_snapshots",
        ["usage_snapshot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_billing_invoices_usage_snapshot_id", "billing_invoices", ["usage_snapshot_id"])
    op.create_index("ix_billing_invoices_provider_invoice_id", "billing_invoices", ["provider_invoice_id"], unique=False)

    op.create_table(
        "billing_payment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_id", sa.String(length=180), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("billing_invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.UniqueConstraint("provider", "event_id", name="uq_billing_payment_event_provider_event"),
    )
    op.create_index("ix_billing_payment_events_tenant_id", "billing_payment_events", ["tenant_id"])
    op.create_index("ix_billing_payment_events_invoice_id", "billing_payment_events", ["invoice_id"])
    op.create_index("ix_billing_payment_events_received_at", "billing_payment_events", ["received_at"])


def downgrade() -> None:
    op.drop_index("ix_billing_payment_events_received_at", table_name="billing_payment_events")
    op.drop_index("ix_billing_payment_events_invoice_id", table_name="billing_payment_events")
    op.drop_index("ix_billing_payment_events_tenant_id", table_name="billing_payment_events")
    op.drop_table("billing_payment_events")

    op.drop_index("ix_billing_invoices_provider_invoice_id", table_name="billing_invoices")
    op.drop_index("ix_billing_invoices_usage_snapshot_id", table_name="billing_invoices")
    op.drop_constraint("fk_billing_invoices_usage_snapshot_id", "billing_invoices", type_="foreignkey")
    op.drop_column("billing_invoices", "finalized_at")
    op.drop_column("billing_invoices", "provider_invoice_id")
    op.drop_column("billing_invoices", "period_end")
    op.drop_column("billing_invoices", "period_start")
    op.drop_column("billing_invoices", "usage_snapshot_id")

    op.drop_column("usage_snapshots", "period_end")
    op.drop_column("usage_snapshots", "period_start")
    op.drop_column("tenant_subscriptions", "grace_ends_at")
    op.drop_column("tenant_subscriptions", "past_due_since")
