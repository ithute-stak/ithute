"""add finance documents, invoice items and credit notes

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
        "finance_invoice_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), server_default="1", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("details", sa.String(length=1200), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rate_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position >= 1", name="ck_finance_invoice_items_position"),
        sa.CheckConstraint("quantity >= 1", name="ck_finance_invoice_items_quantity"),
        sa.CheckConstraint("rate_minor >= 0", name="ck_finance_invoice_items_rate"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_finance_invoice_items_tax"),
        sa.ForeignKeyConstraint(["invoice_id"], ["finance_invoices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_invoice_items_invoice_id", "finance_invoice_items", ["invoice_id"])

    # Preserve every existing invoice as a one-line invoice item before the new UI starts using multiple lines.
    op.execute("""
        INSERT INTO finance_invoice_items
            (id, invoice_id, position, description, details, quantity, rate_minor, tax_minor)
        SELECT gen_random_uuid(), id, 1, description, details, quantity, rate_minor, tax_minor
        FROM finance_invoices
    """)

    op.create_table(
        "finance_credit_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credit_number", sa.String(length=80), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_finance_credit_notes_amount"),
        sa.ForeignKeyConstraint(["invoice_id"], ["finance_invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credit_number"),
    )
    op.create_index("ix_finance_credit_notes_credit_number", "finance_credit_notes", ["credit_number"])
    op.create_index("ix_finance_credit_notes_invoice_id", "finance_credit_notes", ["invoice_id"])
    op.create_index("ix_finance_credit_notes_created_by_user_id", "finance_credit_notes", ["created_by_user_id"])
    op.create_index("ix_finance_credit_notes_created_at", "finance_credit_notes", ["created_at"])

    op.create_table(
        "finance_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_number", sa.String(length=80), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="draft", nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_name", sa.String(length=180), nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("client_address", sa.String(length=500), server_default="", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="LSL", nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_minor", sa.Integer(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("payment_terms_days", sa.Integer(), server_default="7", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("converted_invoice_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("document_type IN ('quotation','proforma')", name="ck_finance_documents_type"),
        sa.CheckConstraint("status IN ('draft','sent','accepted','rejected','converted')", name="ck_finance_documents_status"),
        sa.CheckConstraint("subtotal_minor >= 0", name="ck_finance_documents_subtotal"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_finance_documents_tax"),
        sa.CheckConstraint("total_minor >= 0", name="ck_finance_documents_total"),
        sa.CheckConstraint("payment_terms_days >= 0 AND payment_terms_days <= 365", name="ck_finance_documents_terms"),
        sa.ForeignKeyConstraint(["client_id"], ["finance_clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["converted_invoice_id"], ["finance_invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_number"),
    )
    op.create_index("ix_finance_documents_document_number", "finance_documents", ["document_number"])
    op.create_index("ix_finance_documents_document_type", "finance_documents", ["document_type"])
    op.create_index("ix_finance_documents_status", "finance_documents", ["status"])
    op.create_index("ix_finance_documents_client_id", "finance_documents", ["client_id"])
    op.create_index("ix_finance_documents_recipient_email", "finance_documents", ["recipient_email"])
    op.create_index("ix_finance_documents_converted_invoice_id", "finance_documents", ["converted_invoice_id"])
    op.create_index("ix_finance_documents_created_by_user_id", "finance_documents", ["created_by_user_id"])
    op.create_index("ix_finance_documents_created_at", "finance_documents", ["created_at"])

    op.create_table(
        "finance_document_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), server_default="1", nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("details", sa.String(length=1200), server_default="", nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rate_minor", sa.Integer(), nullable=False),
        sa.Column("tax_minor", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("position >= 1", name="ck_finance_document_items_position"),
        sa.CheckConstraint("quantity >= 1", name="ck_finance_document_items_quantity"),
        sa.CheckConstraint("rate_minor >= 0", name="ck_finance_document_items_rate"),
        sa.CheckConstraint("tax_minor >= 0", name="ck_finance_document_items_tax"),
        sa.ForeignKeyConstraint(["document_id"], ["finance_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_document_items_document_id", "finance_document_items", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_finance_document_items_document_id", table_name="finance_document_items")
    op.drop_table("finance_document_items")

    op.drop_index("ix_finance_documents_created_at", table_name="finance_documents")
    op.drop_index("ix_finance_documents_created_by_user_id", table_name="finance_documents")
    op.drop_index("ix_finance_documents_converted_invoice_id", table_name="finance_documents")
    op.drop_index("ix_finance_documents_recipient_email", table_name="finance_documents")
    op.drop_index("ix_finance_documents_client_id", table_name="finance_documents")
    op.drop_index("ix_finance_documents_status", table_name="finance_documents")
    op.drop_index("ix_finance_documents_document_type", table_name="finance_documents")
    op.drop_index("ix_finance_documents_document_number", table_name="finance_documents")
    op.drop_table("finance_documents")

    op.drop_index("ix_finance_credit_notes_created_at", table_name="finance_credit_notes")
    op.drop_index("ix_finance_credit_notes_created_by_user_id", table_name="finance_credit_notes")
    op.drop_index("ix_finance_credit_notes_invoice_id", table_name="finance_credit_notes")
    op.drop_index("ix_finance_credit_notes_credit_number", table_name="finance_credit_notes")
    op.drop_table("finance_credit_notes")

    op.drop_index("ix_finance_invoice_items_invoice_id", table_name="finance_invoice_items")
    op.drop_table("finance_invoice_items")
