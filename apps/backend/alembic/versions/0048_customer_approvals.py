"""customer approval state

Revision ID: 0048_customer_approvals
Revises: 0047_hosting_git_webhooks
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0048_customer_approvals"
down_revision = "0047_hosting_git_webhooks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("requested_plan_code", sa.String(length=50), nullable=True))
    op.add_column("tenants", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tenants",
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("tenants", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tenants", sa.Column("rejection_reason", sa.String(length=500), nullable=True))
    op.create_index("ix_tenants_approved_at", "tenants", ["approved_at"])
    op.create_index("ix_tenants_rejected_at", "tenants", ["rejected_at"])

    # Existing tenants predate the application-approval workflow. Preserve their
    # current access by treating them as already approved.
    op.execute("UPDATE tenants SET approved_at = COALESCE(created_at, now()) WHERE approved_at IS NULL")


def downgrade():
    op.drop_index("ix_tenants_rejected_at", table_name="tenants")
    op.drop_index("ix_tenants_approved_at", table_name="tenants")
    op.drop_column("tenants", "rejection_reason")
    op.drop_column("tenants", "rejected_at")
    op.drop_column("tenants", "approved_by_user_id")
    op.drop_column("tenants", "approved_at")
    op.drop_column("tenants", "requested_plan_code")
