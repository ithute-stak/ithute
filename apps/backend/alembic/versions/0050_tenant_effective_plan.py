"""tenant base plan for effective addon entitlements

Revision ID: 0050_effective_plan
Revises: 0049_hosting_catalog
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0050_effective_plan"
down_revision = "0049_hosting_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tenant_subscriptions",
        sa.Column(
            "base_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("billing_plans.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_tenant_subscriptions_base_plan_id", "tenant_subscriptions", ["base_plan_id"])
    op.execute("UPDATE tenant_subscriptions SET base_plan_id = plan_id WHERE base_plan_id IS NULL")


def downgrade():
    op.drop_index("ix_tenant_subscriptions_base_plan_id", table_name="tenant_subscriptions")
    op.drop_column("tenant_subscriptions", "base_plan_id")
