"""add finance roles, client portal access and delivery events

Revision ID: 0035_finance_completion
Revises: 0034_finance_governance
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0035_finance_completion"
down_revision = "0034_finance_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_role_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('viewer','clerk','approver','admin')", name="ck_finance_role_grant_role"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_finance_role_grant_user"),
    )
    for column in ["user_id", "role", "active", "granted_by_user_id"]:
        op.create_index(f"ix_finance_role_grants_{column}", "finance_role_grants", [column])

    op.create_table(
        "finance_portal_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["finance_clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    for column in ["client_id", "token_hash", "expires_at", "created_by_user_id"]:
        op.create_index(f"ix_finance_portal_access_{column}", "finance_portal_access", [column])

    op.create_table(
        "finance_delivery_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=80), server_default="finance_smtp", nullable=False),
        sa.Column("provider_message_id", sa.String(length=320), server_default="", nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("event_type IN ('accepted','delivered','deferred','bounced','failed')", name="ck_finance_delivery_event_type"),
        sa.ForeignKeyConstraint(["invoice_id"], ["finance_invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ["invoice_id", "event_type", "provider_message_id", "occurred_at"]:
        op.create_index(f"ix_finance_delivery_events_{column}", "finance_delivery_events", [column])


def downgrade() -> None:
    op.drop_table("finance_delivery_events")
    op.drop_table("finance_portal_access")
    op.drop_table("finance_role_grants")
