"""hardware intelligence prediction fields

Revision ID: 0080_hardware_prediction
Revises: 0079_hardware_intelligence
"""

from alembic import op
import sqlalchemy as sa

revision = "0080_hardware_prediction"
down_revision = "0079_hardware_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hardware_telemetry_snapshots", sa.Column("predictive_risk_score", sa.Integer(), nullable=True))
    op.add_column("hardware_telemetry_snapshots", sa.Column("predictive_state", sa.String(length=24), nullable=True))
    op.add_column("hardware_telemetry_snapshots", sa.Column("predictive_confidence", sa.Float(), nullable=True))
    op.add_column("hardware_telemetry_snapshots", sa.Column("predictive_evidence_json", sa.Text(), nullable=False, server_default="[]"))
    op.create_index("ix_hardware_telemetry_predictive_state", "hardware_telemetry_snapshots", ["predictive_state"])


def downgrade() -> None:
    op.drop_index("ix_hardware_telemetry_predictive_state", table_name="hardware_telemetry_snapshots")
    op.drop_column("hardware_telemetry_snapshots", "predictive_evidence_json")
    op.drop_column("hardware_telemetry_snapshots", "predictive_confidence")
    op.drop_column("hardware_telemetry_snapshots", "predictive_state")
    op.drop_column("hardware_telemetry_snapshots", "predictive_risk_score")
