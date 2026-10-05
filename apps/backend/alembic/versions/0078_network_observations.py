"""add infrastructure network observations

Revision ID: 0078_network_observations
Revises: 0077_resource_reservations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0078_network_observations"
down_revision = "0077_resource_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_network_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("samples", sa.Integer(), nullable=False),
        sa.Column("successes", sa.Integer(), nullable=False),
        sa.Column("reachable", sa.Boolean(), nullable=False),
        sa.Column("connect_loss_percent", sa.Float(), nullable=False),
        sa.Column("latency_min_ms", sa.Float(), nullable=True),
        sa.Column("latency_average_ms", sa.Float(), nullable=True),
        sa.Column("latency_max_ms", sa.Float(), nullable=True),
        sa.Column("jitter_average_ms", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("port >= 1 AND port <= 65535", name="ck_infra_net_obs_port"),
        sa.CheckConstraint("samples >= 1 AND samples <= 10", name="ck_infra_net_obs_samples"),
        sa.CheckConstraint("successes >= 0 AND successes <= samples", name="ck_infra_net_obs_successes"),
        sa.CheckConstraint("connect_loss_percent >= 0 AND connect_loss_percent <= 100", name="ck_infra_net_obs_loss"),
        sa.CheckConstraint("source_server_id <> target_server_id", name="ck_infra_net_obs_distinct_servers"),
    )
    op.create_index("ix_infra_net_obs_source", "infrastructure_network_observations", ["source_server_id"])
    op.create_index("ix_infra_net_obs_target", "infrastructure_network_observations", ["target_server_id"])
    op.create_index("ix_infra_net_obs_created", "infrastructure_network_observations", ["created_at"])
    op.create_index(
        "ix_infra_net_obs_source_target_created",
        "infrastructure_network_observations",
        ["source_server_id", "target_server_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_infra_net_obs_source_target_created", table_name="infrastructure_network_observations")
    op.drop_index("ix_infra_net_obs_created", table_name="infrastructure_network_observations")
    op.drop_index("ix_infra_net_obs_target", table_name="infrastructure_network_observations")
    op.drop_index("ix_infra_net_obs_source", table_name="infrastructure_network_observations")
    op.drop_table("infrastructure_network_observations")
