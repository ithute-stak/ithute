"""resumable zero-loss mail migration cutover tracking

Revision ID: 0053_mail_migration_cutover
Revises: 0052_catalog_lifecycle
"""

from alembic import op
import sqlalchemy as sa

revision = "0053_mail_migration_cutover"
down_revision = "0052_catalog_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_migration_jobs", sa.Column("phase", sa.String(24), nullable=False, server_default="initial"))
    op.add_column("mail_migration_jobs", sa.Column("messages_seen", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mail_migration_jobs", sa.Column("messages_skipped", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mail_migration_jobs", sa.Column("messages_failed", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mail_migration_jobs", sa.Column("failure_summary", sa.Text(), nullable=True))
    op.add_column("mail_migration_jobs", sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_mail_migration_jobs_phase", "mail_migration_jobs", ["phase"])


def downgrade():
    op.drop_index("ix_mail_migration_jobs_phase", table_name="mail_migration_jobs")
    op.drop_column("mail_migration_jobs", "last_sync_at")
    op.drop_column("mail_migration_jobs", "failure_summary")
    op.drop_column("mail_migration_jobs", "messages_failed")
    op.drop_column("mail_migration_jobs", "messages_skipped")
    op.drop_column("mail_migration_jobs", "messages_seen")
    op.drop_column("mail_migration_jobs", "phase")
