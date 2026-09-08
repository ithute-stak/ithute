"""phase 5 submission approval evidence

Revision ID: 0007_phase5_submission_evidence
Revises: 0006_phase5_tender_management
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_phase5_submission_evidence"
down_revision = "0006_phase5_tender_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tender_submissions", sa.Column("approval_request_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tender_submissions_approval_request_id",
        "tender_submissions",
        "approval_requests",
        ["approval_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tender_submissions_approval_request_id", "tender_submissions", ["approval_request_id"])


def downgrade() -> None:
    op.drop_index("ix_tender_submissions_approval_request_id", table_name="tender_submissions")
    op.drop_constraint("fk_tender_submissions_approval_request_id", "tender_submissions", type_="foreignkey")
    op.drop_column("tender_submissions", "approval_request_id")
