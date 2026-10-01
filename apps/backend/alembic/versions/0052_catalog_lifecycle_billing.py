"""package lifecycle, plan changes and recurring add-on billing

Revision ID: 0052_catalog_lifecycle
Revises: 0051_commercial_ops_v2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0052_catalog_lifecycle"
down_revision = "0051_commercial_ops_v2"
branch_labels = None
depends_on = None

LEGACY_CODES = ("starter", "grow", "business", "professional", "enterprise")


def upgrade():
    op.add_column("billing_plans", sa.Column("lifecycle_state", sa.String(24), nullable=False, server_default="sellable"))
    op.add_column("billing_plans", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_billing_plans_lifecycle_state", "billing_plans", ["lifecycle_state"])

    op.add_column(
        "tenant_subscriptions",
        sa.Column("pending_plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("billing_plans.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column("tenant_subscriptions", sa.Column("pending_plan_effective_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_tenant_subscriptions_pending_plan_id", "tenant_subscriptions", ["pending_plan_id"])

    op.add_column("tenant_addons", sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tenant_addons", sa.Column("setup_fee_applied", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tenant_addons", sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenant_addons", sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE billing_plans SET lifecycle_state='legacy', customer_visible=false "
            "WHERE code = ANY(:codes)"
        ),
        {"codes": list(LEGACY_CODES)},
    )
    bind.execute(sa.text("UPDATE billing_plans SET lifecycle_state='hidden' WHERE customer_visible=false AND lifecycle_state='sellable' AND code NOT LIKE 'effective-%'"))
    bind.execute(sa.text("UPDATE billing_plans SET lifecycle_state='hidden' WHERE code LIKE 'effective-%'"))


def downgrade():
    op.drop_column("tenant_addons", "current_period_end")
    op.drop_column("tenant_addons", "current_period_start")
    op.drop_column("tenant_addons", "setup_fee_applied")
    op.drop_column("tenant_addons", "cancel_at_period_end")
    op.drop_index("ix_tenant_subscriptions_pending_plan_id", table_name="tenant_subscriptions")
    op.drop_column("tenant_subscriptions", "pending_plan_effective_at")
    op.drop_column("tenant_subscriptions", "pending_plan_id")
    op.drop_index("ix_billing_plans_lifecycle_state", table_name="billing_plans")
    op.drop_column("billing_plans", "retired_at")
    op.drop_column("billing_plans", "lifecycle_state")
