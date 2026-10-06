"""persist hardware AI model breakdown

Revision ID: 0085_hw_ai_models
Revises: 0084_hw_remediation_outcomes
Create Date: 2026-10-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0085_hw_ai_models"
down_revision = "0084_hw_remediation_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hardware_telemetry_snapshots",
        sa.Column("predictive_models_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("hardware_telemetry_snapshots", "predictive_models_json")
