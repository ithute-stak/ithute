"""store hardware model artifact payload

Revision ID: 0089_hardware_model_artifact
Revises: 0088_hardware_model_registry
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0089_hardware_model_artifact"
down_revision = "0088_hardware_model_registry"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hardware_model_versions",
        sa.Column("artifact_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("hardware_model_versions", "artifact_json")
