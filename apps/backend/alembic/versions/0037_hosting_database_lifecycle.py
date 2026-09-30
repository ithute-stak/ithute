"""add hosting database operation lifecycle

Revision ID: 0037_hosting_database_lifecycle
Revises: 0036_shared_hosting_resources
"""

from alembic import op
import sqlalchemy as sa

revision = "0037_hosting_database_lifecycle"
down_revision = "0036_shared_hosting_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_hosting_database_status", "hosting_databases", type_="check")
    op.create_check_constraint(
        "ck_hosting_database_status",
        "hosting_databases",
        "status IN ('queued','working','ready','suspended','failed','deleting')",
    )
    op.add_column("hosting_databases", sa.Column("operation", sa.String(length=24), server_default="provision", nullable=False))
    op.add_column("hosting_databases", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hosting_databases", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hosting_databases", sa.Column("failure_message", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_hosting_database_operation",
        "hosting_databases",
        "operation IN ('none','provision','rotate','suspend','resume','delete')",
    )
    op.execute("UPDATE hosting_databases SET status = 'queued', operation = 'provision' WHERE status = 'provisioning'")


def downgrade() -> None:
    op.execute("UPDATE hosting_databases SET status = 'provisioning' WHERE status IN ('queued','working')")
    op.drop_constraint("ck_hosting_database_operation", "hosting_databases", type_="check")
    op.drop_column("hosting_databases", "failure_message")
    op.drop_column("hosting_databases", "completed_at")
    op.drop_column("hosting_databases", "claimed_at")
    op.drop_column("hosting_databases", "operation")
    op.drop_constraint("ck_hosting_database_status", "hosting_databases", type_="check")
    op.create_check_constraint(
        "ck_hosting_database_status",
        "hosting_databases",
        "status IN ('provisioning','ready','suspended','failed','deleting')",
    )