"""Phase 17 project closeout and defects liability.

Revision ID: 0018_phase17_closeout
Revises: 0017_phase16_rollout
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_phase17_closeout"
down_revision = "0017_phase16_rollout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_closeouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("closeout_number", sa.String(80), nullable=False),
        sa.Column("practical_completion_date", sa.Date(), nullable=False),
        sa.Column("defects_liability_end_date", sa.Date(), nullable=False),
        sa.Column("final_account_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("retention_release_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("practical_completion_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("client_acceptance_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("final_account_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("retention_release_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "closeout_number", name="uq_project_closeout_company_number"),
        sa.UniqueConstraint("project_id", name="uq_project_closeout_project"),
    )
    op.create_table(
        "closeout_checklist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("closeout_id", sa.Integer(), sa.ForeignKey("project_closeouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("completed_by", sa.String(255)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("closeout_id", "title", name="uq_closeout_checklist_title"),
    )
    op.create_table(
        "closeout_defects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("closeout_id", sa.Integer(), sa.ForeignKey("project_closeouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("defect_number", sa.String(80), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(24), nullable=False),
        sa.Column("raised_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("evidence_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("closeout_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("raised_by", sa.String(255), nullable=False),
        sa.Column("closed_by", sa.String(255)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "defect_number", name="uq_closeout_defect_company_number"),
    )
    op.create_table(
        "closeout_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("closeout_id", sa.Integer(), sa.ForeignKey("project_closeouts.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(80), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    indexes = {
        "project_closeouts": ("company_id", "branch_id", "site_id", "project_id", "closeout_number", "practical_completion_date", "defects_liability_end_date", "status", "approval_request_id"),
        "closeout_checklist_items": ("company_id", "branch_id", "closeout_id", "item_type", "due_date", "status", "evidence_document_id"),
        "closeout_defects": ("company_id", "branch_id", "site_id", "project_id", "closeout_id", "defect_number", "category", "priority", "raised_date", "due_date", "status", "evidence_document_id", "closeout_document_id"),
        "closeout_audit_events": ("company_id", "branch_id", "site_id", "project_id", "closeout_id", "action", "occurred_at"),
    }
    for table, columns in indexes.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in ("closeout_audit_events", "closeout_defects", "closeout_checklist_items", "project_closeouts"):
        for index in [row["name"] for row in sa.inspect(op.get_bind()).get_indexes(table)]:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
