"""ithute operating platform control plane

Revision ID: 0013_ithute_operating_core
Revises: 0012_merge_consolidated_heads
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_ithute_operating_core"
down_revision = "0012_merge_consolidated_heads"
branch_labels = None
depends_on = None

product_status = postgresql.ENUM("unknown", "online", "degraded", "maintenance", "offline", name="product_operational_status", create_type=False)
event_status = postgresql.ENUM("accepted", "processing", "delivered", "failed", name="platform_event_status", create_type=False)
grant_status = postgresql.ENUM("demo", "active", "suspended", "expired", name="subscription_grant_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (product_status, event_status, grant_status):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "ithute_products",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(80), nullable=False, server_default="business"),
        sa.Column("manifest_version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("version", sa.String(80), nullable=True),
        sa.Column("operational_status", product_status, nullable=False, server_default="unknown"),
        sa.Column("public_url", sa.String(512), nullable=True),
        sa.Column("api_url", sa.String(512), nullable=True),
        sa.Column("health_url", sa.String(512), nullable=True),
        sa.Column("deployment_target", sa.String(255), nullable=True),
        sa.Column("deployment_mode", sa.String(80), nullable=False, server_default="isolated"),
        sa.Column("database_ownership", sa.String(80), nullable=False, server_default="product"),
        sa.Column("database_engine", sa.String(80), nullable=True),
        sa.Column("auth_mode", sa.String(80), nullable=False, server_default="central"),
        sa.Column("push_mode", sa.String(80), nullable=False, server_default="central"),
        sa.Column("realtime_mode", sa.String(80), nullable=False, server_default="central"),
        sa.Column("event_bus_mode", sa.String(80), nullable=False, server_default="central"),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "ithute_product_heartbeats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", product_status, nullable=False),
        sa.Column("version", sa.String(80), nullable=True),
        sa.Column("database_status", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("auth_status", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("push_status", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("realtime_status", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("container_summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ithute_product_heartbeats_product_id", "ithute_product_heartbeats", ["product_id"])
    op.create_index("ix_ithute_product_heartbeats_product_observed", "ithute_product_heartbeats", ["product_id", "observed_at"])

    op.create_table(
        "ithute_platform_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_event_id", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("subject", sa.String(255), nullable=True),
        sa.Column("tenant_ref", sa.String(255), nullable=True),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", event_status, nullable=False, server_default="accepted"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("product_id", "source_event_id", name="uq_ithute_event_product_source"),
    )
    op.create_index("ix_ithute_platform_events_product_id", "ithute_platform_events", ["product_id"])
    op.create_index("ix_ithute_platform_events_event_type", "ithute_platform_events", ["event_type"])
    op.create_index("ix_ithute_platform_events_trace_id", "ithute_platform_events", ["trace_id"])
    op.create_index("ix_ithute_platform_events_type_created", "ithute_platform_events", ["event_type", "created_at"])

    op.create_table(
        "ithute_platform_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recipient_sub", sa.String(255), nullable=False),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ithute_platform_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False, server_default="general"),
        sa.Column("action_url", sa.String(1024), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ithute_platform_notifications_recipient_sub", "ithute_platform_notifications", ["recipient_sub"])
    op.create_index("ix_ithute_notification_recipient_created", "ithute_platform_notifications", ["recipient_sub", "created_at"])

    op.create_table(
        "ithute_subscription_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_type", sa.String(40), nullable=False),
        sa.Column("subject_id", sa.String(255), nullable=False),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(100), nullable=False, server_default="demo"),
        sa.Column("status", grant_status, nullable=False, server_default="demo"),
        sa.Column("features_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("subject_type", "subject_id", "product_id", name="uq_ithute_subscription_subject_product"),
    )

    op.create_table(
        "ithute_product_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("command_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="queued"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("requested_by", sa.String(255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ithute_commands_product_created", "ithute_product_commands", ["product_id", "created_at"])


def downgrade() -> None:
    for table in (
        "ithute_product_commands",
        "ithute_subscription_grants",
        "ithute_platform_notifications",
        "ithute_platform_events",
        "ithute_product_heartbeats",
        "ithute_products",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for enum in (grant_status, event_status, product_status):
        enum.drop(bind, checkfirst=True)
