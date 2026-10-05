"""add external infrastructure fencing

Revision ID: 0086_external_fencing
Revises: 0085_database_failover_attempts
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0086_external_fencing"
down_revision = "0085_database_failover_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_fence_controllers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("token_hint", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('provider_api','hypervisor','power_controller')", name="ck_infrastructure_fence_controller_kind"),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_infrastructure_fence_controller_status"),
    )
    op.create_index("ix_infrastructure_fence_controllers_provider", "infrastructure_fence_controllers", ["provider"])
    op.create_index("ix_infrastructure_fence_controllers_status", "infrastructure_fence_controllers", ["status"])

    op.create_table(
        "infrastructure_fence_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("controller_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_fence_controllers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("database_failover_attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hosting_database_failover_attempts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("claim_token_hash", sa.String(length=64), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("observed_state", sa.String(length=24), nullable=True),
        sa.Column("provider_operation_id", sa.String(length=255), nullable=True),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued','claimed','succeeded','failed')", name="ck_infrastructure_fence_attempt_status"),
        sa.CheckConstraint("observed_state IS NULL OR observed_state IN ('powered_off','isolated')", name="ck_infrastructure_fence_observed_state"),
    )
    op.create_index("ix_infrastructure_fence_attempts_server_id", "infrastructure_fence_attempts", ["server_id"])
    op.create_index("ix_infrastructure_fence_attempts_controller_id", "infrastructure_fence_attempts", ["controller_id"])
    op.create_index("ix_infrastructure_fence_attempts_failover_id", "infrastructure_fence_attempts", ["database_failover_attempt_id"])
    op.create_index("ix_infrastructure_fence_attempts_status", "infrastructure_fence_attempts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_fence_attempts_status", table_name="infrastructure_fence_attempts")
    op.drop_index("ix_infrastructure_fence_attempts_failover_id", table_name="infrastructure_fence_attempts")
    op.drop_index("ix_infrastructure_fence_attempts_controller_id", table_name="infrastructure_fence_attempts")
    op.drop_index("ix_infrastructure_fence_attempts_server_id", table_name="infrastructure_fence_attempts")
    op.drop_table("infrastructure_fence_attempts")
    op.drop_index("ix_infrastructure_fence_controllers_status", table_name="infrastructure_fence_controllers")
    op.drop_index("ix_infrastructure_fence_controllers_provider", table_name="infrastructure_fence_controllers")
    op.drop_table("infrastructure_fence_controllers")
