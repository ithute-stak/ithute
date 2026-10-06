"""add mail threat model registry

Revision ID: 0089_mail_threat_models
Revises: 0088_hardware_model_registry
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0089_mail_threat_models"
down_revision = "0088_hardware_model_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_threat_model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(96), nullable=False),
        sa.Column("algorithm", sa.String(96), nullable=False),
        sa.Column("lifecycle_state", sa.String(32), nullable=False, server_default="candidate"),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("training_metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("shadow_metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("promotion_evidence_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rollback_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_mail_threat_model_name_version"),
    )
    op.create_index("ix_mail_threat_model_state", "mail_threat_model_versions", ["lifecycle_state"])
    op.create_index("ix_mail_threat_model_created", "mail_threat_model_versions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_mail_threat_model_created", table_name="mail_threat_model_versions")
    op.drop_index("ix_mail_threat_model_state", table_name="mail_threat_model_versions")
    op.drop_table("mail_threat_model_versions")
