"""add finance commercial documents and audit log

Revision ID: 0031_finance_documents
Revises: 0030_finance_clients_payments
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0031_finance_documents"
down_revision = "0030_finance_clients_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_commercial_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_number", sa.String(length=80), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("converted_invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_name", sa.String(length=180), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("client_address", sa.String(length=500), server_default="", nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="LSL", nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("subtotal_minor >= 0", name="ck_finance_documents_subtotal"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_finance_documents_tax"),
        sa.CheckConstraint("total_minor >= 0", name="ck_finance_documents_total"),
        sa.ForeignKeyConstraint(["client_id"], ["finance_clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_id"], ["finance_commercial_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_invoice_id"], ["finance_invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_invoice_id"], ["finance_invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_number"),
    )
    op.create_index("ix_finance_commercial_documents_document_number", "finance_commercial_documents", ["document_number"], unique=True)
    op.create_index("ix_finance_commercial_documents_document_type", "finance_commercial_documents", ["document_type"])
    op.create_index("ix_finance_commercial_documents_status", "finance_commercial_documents", ["status"])
    op.create_index("ix_finance_commercial_documents_client_id", "finance_commercial_documents", ["client_id"])
    op.create_index("ix_finance_commercial_documents_source_invoice_id", "finance_commercial_documents", ["source_invoice_id"])
    op.create_index("ix_finance_commercial_documents_recipient_email", "finance_commercial_documents", ["recipient_email"])
    op.create_index("ix_finance_commercial_documents_created_at", "finance_commercial_documents", ["created_at"])

    op.create_table(
        "finance_commercial_document_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), server_default="1", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("details", sa.String(length=1200), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("unit_rate_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("line_subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("line_total_minor", sa.Integer(), nullable=False),
        sa.CheckConstraint("position >= 1", name="ck_finance_document_items_position"),
        sa.CheckConstraint("quantity >= 1", name="ck_finance_document_items_quantity"),
        sa.CheckConstraint("unit_rate_minor >= 0", name="ck_finance_document_items_rate"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_finance_document_items_tax"),
        sa.ForeignKeyConstraint(["document_id"], ["finance_commercial_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_commercial_document_items_document_id", "finance_commercial_document_items", ["document_id"])

    op.create_table(
        "finance_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("summary", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_audit_events_entity_type", "finance_audit_events", ["entity_type"])
    op.create_index("ix_finance_audit_events_entity_id", "finance_audit_events", ["entity_id"])
    op.create_index("ix_finance_audit_events_action", "finance_audit_events", ["action"])
    op.create_index("ix_finance_audit_events_actor_user_id", "finance_audit_events", ["actor_user_id"])
    op.create_index("ix_finance_audit_events_created_at", "finance_audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_finance_audit_events_created_at", table_name="finance_audit_events")
    op.drop_index("ix_finance_audit_events_actor_user_id", table_name="finance_audit_events")
    op.drop_index("ix_finance_audit_events_action", table_name="finance_audit_events")
    op.drop_index("ix_finance_audit_events_entity_id", table_name="finance_audit_events")
    op.drop_index("ix_finance_audit_events_entity_type", table_name="finance_audit_events")
    op.drop_table("finance_audit_events")

    op.drop_index("ix_finance_commercial_document_items_document_id", table_name="finance_commercial_document_items")
    op.drop_table("finance_commercial_document_items")

    op.drop_index("ix_finance_commercial_documents_created_at", table_name="finance_commercial_documents")
    op.drop_index("ix_finance_commercial_documents_recipient_email", table_name="finance_commercial_documents")
    op.drop_index("ix_finance_commercial_documents_source_invoice_id", table_name="finance_commercial_documents")
    op.drop_index("ix_finance_commercial_documents_client_id", table_name="finance_commercial_documents")
    op.drop_index("ix_finance_commercial_documents_status", table_name="finance_commercial_documents")
    op.drop_index("ix_finance_commercial_documents_document_type", table_name="finance_commercial_documents")
    op.drop_index("ix_finance_commercial_documents_document_number", table_name="finance_commercial_documents")
    op.drop_table("finance_commercial_documents")
