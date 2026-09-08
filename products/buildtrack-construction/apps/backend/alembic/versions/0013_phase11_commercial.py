"""Phase 11 cost, commercial, client and claims control.

Revision ID: 0013_phase11_commercial
Revises: 0012_algorithmic_assist
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_phase11_commercial"
down_revision = "0012_algorithmic_assist"
branch_labels = None
depends_on = None


def _ref(table: str, nullable: bool = True, *, restrict: bool = False) -> sa.Column:
    return sa.Column(table[:-1] + "_id", sa.Integer(), sa.ForeignKey(f"{table}.id", ondelete="RESTRICT" if restrict else "SET NULL"), nullable=nullable)


def _audit_table() -> None:
    op.create_table(
        "commercial_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=100)),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("company_id", "branch_id", "site_id", "project_id", "action", "entity_type", "occurred_at"):
        op.create_index(f"ix_commercial_audit_events_{column}", "commercial_audit_events", [column])


def upgrade() -> None:
    op.create_table(
        "client_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("contract_number", sa.String(length=80), nullable=False), sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("client_name", sa.String(length=240), nullable=False), sa.Column("client_reference", sa.String(length=180)),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("completion_date", sa.Date(), nullable=False),
        sa.Column("original_contract_sum", sa.Numeric(18, 2), nullable=False), sa.Column("retention_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False), sa.Column("contract_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")), sa.Column("approved_snapshot", sa.JSON()), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "contract_number", name="uq_client_contract_company_number"), sa.UniqueConstraint("project_id", name="uq_client_contract_project"),
    )
    op.create_table(
        "client_variations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("client_contracts.id", ondelete="CASCADE"), nullable=False), sa.Column("variation_number", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("value", sa.Numeric(18, 2), nullable=False),
        sa.Column("time_extension_days", sa.Integer(), nullable=False), sa.Column("status", sa.String(length=24), nullable=False), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")), sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("contract_id", "variation_number", name="uq_client_variation_number"),
    )
    op.create_table(
        "project_cost_transactions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False), sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transaction_number", sa.String(length=80), nullable=False), sa.Column("transaction_date", sa.Date(), nullable=False), sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("cost_type", sa.String(length=48), nullable=False), sa.Column("cost_code", sa.String(length=80)), sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False), sa.Column("source_type", sa.String(length=64)), sa.Column("source_reference", sa.String(length=160)),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("status", sa.String(length=24), nullable=False), sa.Column("reversal_of_id", sa.Integer(), sa.ForeignKey("project_cost_transactions.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()), sa.Column("recorded_by", sa.String(length=255), nullable=False), sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "transaction_number", name="uq_project_cost_transaction_number"),
    )
    op.create_table(
        "client_valuations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("client_contracts.id", ondelete="CASCADE"), nullable=False), sa.Column("valuation_number", sa.String(length=80), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False), sa.Column("gross_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("previous_certified", sa.Numeric(18, 2), nullable=False), sa.Column("cumulative_certified", sa.Numeric(18, 2), nullable=False), sa.Column("retention_deduction", sa.Numeric(18, 2), nullable=False), sa.Column("other_deductions", sa.Numeric(18, 2), nullable=False), sa.Column("net_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False), sa.Column("evidence_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()), sa.Column("prepared_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("contract_id", "valuation_number", name="uq_client_valuation_number"),
    )
    op.create_table(
        "client_invoices",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("client_contracts.id", ondelete="CASCADE"), nullable=False), sa.Column("valuation_id", sa.Integer(), sa.ForeignKey("client_valuations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invoice_number", sa.String(length=80), nullable=False), sa.Column("invoice_date", sa.Date(), nullable=False), sa.Column("due_date", sa.Date()),
        sa.Column("gross_amount", sa.Numeric(18, 2), nullable=False), sa.Column("retention_amount", sa.Numeric(18, 2), nullable=False), sa.Column("net_amount", sa.Numeric(18, 2), nullable=False), sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False), sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("invoice_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "invoice_number", name="uq_client_invoice_number"), sa.UniqueConstraint("valuation_id"),
    )
    op.create_table(
        "client_receipts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("client_invoices.id", ondelete="RESTRICT"), nullable=False), sa.Column("receipt_reference", sa.String(length=120), nullable=False), sa.Column("receipt_date", sa.Date(), nullable=False), sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("payment_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("notes", sa.Text()), sa.Column("recorded_by", sa.String(length=255), nullable=False), sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "receipt_reference", name="uq_client_receipt_reference"),
    )
    op.create_table(
        "client_claims",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False), sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("contract_id", sa.Integer(), sa.ForeignKey("client_contracts.id", ondelete="SET NULL")),
        sa.Column("claim_number", sa.String(length=80), nullable=False), sa.Column("claim_type", sa.String(length=48), nullable=False), sa.Column("title", sa.String(length=240), nullable=False), sa.Column("basis", sa.Text(), nullable=False), sa.Column("claimed_amount", sa.Numeric(18, 2), nullable=False), sa.Column("assessed_amount", sa.Numeric(18, 2)),
        sa.Column("notice_date", sa.Date()), sa.Column("response_due_date", sa.Date()), sa.Column("status", sa.String(length=24), nullable=False), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()), sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("submitted_at", sa.DateTime(timezone=True)), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "claim_number", name="uq_client_claim_number"),
    )
    op.create_table(
        "project_cash_flow_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("forecast_month", sa.Date(), nullable=False), sa.Column("expected_inflow", sa.Numeric(18, 2), nullable=False), sa.Column("expected_outflow", sa.Numeric(18, 2), nullable=False), sa.Column("net_cash", sa.Numeric(18, 2), nullable=False), sa.Column("source", sa.String(length=48), nullable=False), sa.Column("status", sa.String(length=24), nullable=False), sa.Column("notes", sa.Text()), sa.Column("prepared_by", sa.String(length=255), nullable=False), sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "forecast_month", name="uq_project_cash_flow_month"),
    )
    for table, columns in {
        "client_contracts": ("company_id", "branch_id", "site_id", "project_id", "cost_centre_id", "contract_number", "client_name", "completion_date", "status", "approval_request_id"),
        "client_variations": ("company_id", "contract_id", "status", "approval_request_id"),
        "project_cost_transactions": ("company_id", "branch_id", "site_id", "project_id", "cost_centre_id", "transaction_number", "transaction_date", "transaction_type", "cost_type", "cost_code", "source_type", "status", "reversal_of_id", "recorded_at"),
        "client_valuations": ("company_id", "contract_id", "period_end", "status", "approval_request_id"),
        "client_invoices": ("company_id", "contract_id", "valuation_id", "invoice_number", "invoice_date", "due_date", "status", "approval_request_id"),
        "client_receipts": ("company_id", "invoice_id", "receipt_date"),
        "client_claims": ("company_id", "branch_id", "site_id", "project_id", "contract_id", "claim_number", "claim_type", "notice_date", "response_due_date", "status", "approval_request_id"),
        "project_cash_flow_forecasts": ("company_id", "project_id", "forecast_month", "status"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    _audit_table()


def downgrade() -> None:
    for table in ("commercial_audit_events", "project_cash_flow_forecasts", "client_claims", "client_receipts", "client_invoices", "client_valuations", "project_cost_transactions", "client_variations", "client_contracts"):
        indexes = [index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)]
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
