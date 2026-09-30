"""add finance governance and approvals

Revision ID: 0034_finance_governance
Revises: 0033_finance_controls_close
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0034_finance_governance"
down_revision = "0033_finance_controls_close"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_governance_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("invoice_approval_threshold_minor", sa.Integer(), server_default="500000", nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("invoice_approval_threshold_minor >= 0", name="ck_finance_governance_invoice_threshold"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_governance_settings_updated_by_user_id", "finance_governance_settings", ["updated_by_user_id"])

    op.create_table(
        "finance_approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("request_note", sa.Text(), server_default="", nullable=False),
        sa.Column("decision_note", sa.Text(), server_default="", nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("resource_type IN ('invoice')", name="ck_finance_approval_resource_type"),
        sa.CheckConstraint("status IN ('pending','approved','rejected')", name="ck_finance_approval_status"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource_type", "resource_id", name="uq_finance_approval_resource"),
    )
    for column in ["resource_type", "resource_id", "status", "requested_by_user_id", "decided_by_user_id"]:
        op.create_index(f"ix_finance_approval_requests_{column}", "finance_approval_requests", [column])


def downgrade() -> None:
    op.drop_table("finance_approval_requests")
    op.drop_table("finance_governance_settings")
