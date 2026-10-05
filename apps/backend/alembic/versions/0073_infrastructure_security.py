"""add infrastructure security snapshots

Revision ID: 0073_infrastructure_security
Revises: 0072_infrastructure_agent_ops
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0073_infrastructure_security"
down_revision = "0072_infrastructure_agent_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "infrastructure_security_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("infrastructure_servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("posture", sa.String(length=24), nullable=False),
        sa.Column("findings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_infrastructure_security_snapshots_server_id", "infrastructure_security_snapshots", ["server_id"])
    op.create_index("ix_infrastructure_security_snapshots_posture", "infrastructure_security_snapshots", ["posture"])
    op.create_index("ix_infrastructure_security_snapshots_fingerprint_sha256", "infrastructure_security_snapshots", ["fingerprint_sha256"])
    op.create_index("ix_infrastructure_security_snapshots_created_at", "infrastructure_security_snapshots", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_infrastructure_security_snapshots_created_at", table_name="infrastructure_security_snapshots")
    op.drop_index("ix_infrastructure_security_snapshots_fingerprint_sha256", table_name="infrastructure_security_snapshots")
    op.drop_index("ix_infrastructure_security_snapshots_posture", table_name="infrastructure_security_snapshots")
    op.drop_index("ix_infrastructure_security_snapshots_server_id", table_name="infrastructure_security_snapshots")
    op.drop_table("infrastructure_security_snapshots")
