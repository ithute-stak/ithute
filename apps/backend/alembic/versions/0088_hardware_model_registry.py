"""hardware model registry and shadow evidence

Revision ID: 0088_hardware_model_registry
Revises: 0087_hardware_failure_labels
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0088_hardware_model_registry"
down_revision = "0087_hardware_failure_labels"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hardware_model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False, server_default="candidate"),
        sa.Column("artifact_uri", sa.Text(), nullable=True),
        sa.Column("feature_schema_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("training_metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("shadow_metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("promotion_evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_hardware_model_name_version"),
    )
    op.create_index("ix_hardware_model_versions_state", "hardware_model_versions", ["lifecycle_state"])
    op.create_index("ix_hardware_model_versions_created_at", "hardware_model_versions", ["created_at"])

    op.create_table(
        "hardware_shadow_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hardware_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hardware_telemetry_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_probability", sa.Float(), nullable=False),
        sa.Column("baseline_probability", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("feature_vector_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("target", sa.Integer(), nullable=True),
        sa.Column("outcome_source", sa.String(length=32), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("model_id", "snapshot_id", name="uq_hardware_shadow_model_snapshot"),
    )
    op.create_index("ix_hardware_shadow_predictions_model_id", "hardware_shadow_predictions", ["model_id"])
    op.create_index("ix_hardware_shadow_predictions_server_id", "hardware_shadow_predictions", ["server_id"])
    op.create_index("ix_hardware_shadow_predictions_snapshot_id", "hardware_shadow_predictions", ["snapshot_id"])
    op.create_index("ix_hardware_shadow_predictions_created_at", "hardware_shadow_predictions", ["created_at"])

    op.create_table(
        "hardware_model_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hardware_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("from_state", sa.String(length=32), nullable=True),
        sa.Column("to_state", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_hardware_model_events_model_id", "hardware_model_events", ["model_id"])
    op.create_index("ix_hardware_model_events_event_type", "hardware_model_events", ["event_type"])
    op.create_index("ix_hardware_model_events_created_at", "hardware_model_events", ["created_at"])


def downgrade():
    op.drop_index("ix_hardware_model_events_created_at", table_name="hardware_model_events")
    op.drop_index("ix_hardware_model_events_event_type", table_name="hardware_model_events")
    op.drop_index("ix_hardware_model_events_model_id", table_name="hardware_model_events")
    op.drop_table("hardware_model_events")
    op.drop_index("ix_hardware_shadow_predictions_created_at", table_name="hardware_shadow_predictions")
    op.drop_index("ix_hardware_shadow_predictions_snapshot_id", table_name="hardware_shadow_predictions")
    op.drop_index("ix_hardware_shadow_predictions_server_id", table_name="hardware_shadow_predictions")
    op.drop_index("ix_hardware_shadow_predictions_model_id", table_name="hardware_shadow_predictions")
    op.drop_table("hardware_shadow_predictions")
    op.drop_index("ix_hardware_model_versions_created_at", table_name="hardware_model_versions")
    op.drop_index("ix_hardware_model_versions_state", table_name="hardware_model_versions")
    op.drop_table("hardware_model_versions")
