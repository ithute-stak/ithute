"""add dashboard-managed OAuth redirect URLs

Revision ID: 0012_app_redirect_uris
Revises: 0011_notification_gateway_client
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_app_redirect_uris"
down_revision = "0006_managed_service_clients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_redirect_uris",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "redirect_uri", name="uq_app_redirect_uri"),
    )
    op.create_index("ix_application_redirect_uris_application_id", "application_redirect_uris", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_application_redirect_uris_application_id", table_name="application_redirect_uris")
    op.drop_table("application_redirect_uris")
