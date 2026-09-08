"""Algorithmic procurement and tender assistants.

Revision ID: 0012_algorithmic_assist
Revises: 0011_phase9_subcontracts
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_algorithmic_assist"
down_revision = "0011_phase9_subcontracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "algorithmic_assistant_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("module", sa.String(length=32), nullable=False),
        sa.Column("analysis_type", sa.String(length=80), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=100), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("source_sha256", sa.String(length=64)),
        sa.Column("rule_version", sa.String(length=32), nullable=False, server_default="algorithmic-v1"),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("company_id", "branch_id", "site_id", "module", "analysis_type", "subject_type", "subject_id", "document_id", "source_sha256", "created_at"):
        op.create_index(f"ix_algorithmic_assistant_analyses_{column}", "algorithmic_assistant_analyses", [column])


def downgrade() -> None:
    for column in ("created_at", "source_sha256", "document_id", "subject_id", "subject_type", "analysis_type", "module", "site_id", "branch_id", "company_id"):
        op.drop_index(f"ix_algorithmic_assistant_analyses_{column}", table_name="algorithmic_assistant_analyses")
    op.drop_table("algorithmic_assistant_analyses")
