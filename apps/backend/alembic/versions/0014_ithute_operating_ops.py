"""ithute operating platform operations

Revision ID: 0014_ithute_operating_ops
Revises: 0013_ithute_operating_core
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014_ithute_operating_ops"
down_revision = "0013_ithute_operating_core"
branch_labels = None
depends_on = None

deployment_status = postgresql.ENUM("queued", "running", "succeeded", "failed", "rolled_back", name="deployment_status", create_type=False)
backup_status = postgresql.ENUM("pending", "running", "ready", "failed", "expired", name="backup_status", create_type=False)
security_severity = postgresql.ENUM("info", "low", "medium", "high", "critical", name="security_severity", create_type=False)

def upgrade() -> None:
    bind = op.get_bind()
    for enum in (deployment_status, backup_status, security_severity):
        enum.create(bind, checkfirst=True)
    op.create_table(
        "ithute_product_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(120), nullable=True),
        sa.Column("source_sha", sa.String(64), nullable=True),
        sa.Column("environment", sa.String(50), nullable=False, server_default="production"),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("status", deployment_status, nullable=False, server_default="queued"),
        sa.Column("initiated_by", sa.String(255), nullable=True),
        sa.Column("backup_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ithute_deployments_product_started", "ithute_product_deployments", ["product_id", "started_at"])

    op.create_table(
        "ithute_product_backups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(80), nullable=False, server_default="database"),
        sa.Column("status", backup_status, nullable=False, server_default="pending"),
        sa.Column("storage_uri", sa.String(1024), nullable=True),
        sa.Column("checksum", sa.String(255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("restore_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ithute_backups_product_created", "ithute_product_backups", ["product_id", "created_at"])

    op.create_table(
        "ithute_security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("severity", security_severity, nullable=False, server_default="info"),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("actor_ref", sa.String(255), nullable=True),
        sa.Column("subject_ref", sa.String(255), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ithute_security_product_created", "ithute_security_events", ["product_id", "created_at"])

    op.create_table(
        "ithute_secret_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False, server_default="docker_secret"),
        sa.Column("reference", sa.String(512), nullable=False),
        sa.Column("version", sa.String(80), nullable=True),
        sa.Column("rotation_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "name", name="uq_ithute_secret_product_name"),
    )

    op.create_table(
        "ithute_developer_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", sa.String(160), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_ref", sa.String(255), nullable=False),
        sa.Column("allowed_products_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("scopes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", name="uq_ithute_developer_client_id"),
    )

    op.create_table(
        "ithute_webhook_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("developer_client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ithute_developer_clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_pattern", sa.String(160), nullable=False),
        sa.Column("target_url", sa.String(1024), nullable=False),
        sa.Column("secret_reference_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ithute_secret_references.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "ithute_support_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("support_ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.String(80), sa.ForeignKey("ithute_products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("organization_ref", sa.String(255), nullable=True),
        sa.Column("user_ref", sa.String(255), nullable=True),
        sa.Column("trace_id", sa.String(128), nullable=True),
        sa.Column("deployment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("support_ticket_id", name="uq_ithute_support_context_ticket"),
    )


def downgrade() -> None:
    for table in (
        "ithute_support_contexts",
        "ithute_webhook_subscriptions",
        "ithute_developer_clients",
        "ithute_secret_references",
        "ithute_security_events",
        "ithute_product_backups",
        "ithute_product_deployments",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for enum in (security_severity, backup_status, deployment_status):
        enum.drop(bind, checkfirst=True)
