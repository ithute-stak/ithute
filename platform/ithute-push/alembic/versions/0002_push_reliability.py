"""add push idempotency and device acknowledgement timestamps

Revision ID: 0002_push_reliability
Revises: 0001_push_delivery
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_push_reliability"
down_revision = "0001_push_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.add_column("messages", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_message_source_idempotency",
        "messages",
        ["source_client_id", "idempotency_key"],
    )
    op.add_column("deliveries", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("deliveries", sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("deliveries", "opened_at")
    op.drop_column("deliveries", "received_at")
    op.drop_constraint("uq_message_source_idempotency", "messages", type_="unique")
    op.drop_column("messages", "request_fingerprint")
    op.drop_column("messages", "idempotency_key")
