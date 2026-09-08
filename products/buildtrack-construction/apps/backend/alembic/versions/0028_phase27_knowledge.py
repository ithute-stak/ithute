"""Phase 27 operational knowledge, SOP and acknowledgement control."""

from alembic import op
import sqlalchemy as sa


revision = "0028_phase27_knowledge"
down_revision = "0027_phase26_support"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("article_number", sa.String(80), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("audience", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("review_due_date", sa.Date()),
        sa.Column("evidence_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("source_ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id", ondelete="SET NULL")),
        sa.Column("source_change_id", sa.Integer(), sa.ForeignKey("change_requests.id", ondelete="SET NULL")),
        sa.Column("prepared_by", sa.String(255), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("published_by", sa.String(255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("retired_by", sa.String(255)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "article_number", name="uq_knowledge_article_number"),
    )
    op.create_table(
        "knowledge_acknowledgements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("knowledge_articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("acknowledged_by", sa.String(255), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", "user_id", name="uq_knowledge_article_user_ack"),
    )
    op.create_table(
        "knowledge_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table, columns in {
        "knowledge_articles": ("company_id", "branch_id", "site_id", "article_number", "category", "audience", "status", "review_due_date", "evidence_document_id", "source_ticket_id", "source_change_id"),
        "knowledge_acknowledgements": ("article_id", "user_id"),
        "knowledge_audit_events": ("company_id", "branch_id", "site_id", "action", "occurred_at"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ("knowledge_audit_events", "knowledge_acknowledgements", "knowledge_articles"):
        for index in [row["name"] for row in sa.inspect(op.get_bind()).get_indexes(table)]:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
