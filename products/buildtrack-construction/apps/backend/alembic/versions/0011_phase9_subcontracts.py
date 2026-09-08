"""Phase 9 subcontract management.

Revision ID: 0011_phase9_subcontracts
Revises: 0010_phase8_procurement
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_phase9_subcontracts"
down_revision = "0010_phase8_procurement"
branch_labels = None
depends_on = None


def _audit_table() -> None:
    op.create_table(
        "subcontract_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False, index=True),
        sa.Column("entity_type", sa.String(length=80), nullable=False, index=True),
        sa.Column("entity_id", sa.String(length=100), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "subcontractors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subcontractor_code", sa.String(length=80), nullable=False),
        sa.Column("legal_name", sa.String(length=240), nullable=False),
        sa.Column("trading_name", sa.String(length=240)), sa.Column("registration_number", sa.String(length=120)), sa.Column("tax_number", sa.String(length=120)),
        sa.Column("contact_name", sa.String(length=180)), sa.Column("email", sa.String(length=255)), sa.Column("phone", sa.String(length=64)), sa.Column("address", sa.Text()),
        sa.Column("trade_categories", sa.JSON(), nullable=False, server_default=sa.text("'[]'")), sa.Column("safety_rating", sa.Numeric(5, 2)), sa.Column("performance_rating", sa.Numeric(5, 2)),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("compliance_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("insurance_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("approved_by", sa.String(length=255)), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "subcontractor_code", name="uq_subcontractor_company_code"),
    )
    op.create_index("ix_subcontractors_company_id", "subcontractors", ["company_id"])
    op.create_index("ix_subcontractors_subcontractor_code", "subcontractors", ["subcontractor_code"])
    op.create_index("ix_subcontractors_legal_name", "subcontractors", ["legal_name"])
    op.create_index("ix_subcontractors_status", "subcontractors", ["status"])

    op.create_table(
        "subcontract_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")), sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("package_number", sa.String(length=80), nullable=False), sa.Column("package_code", sa.String(length=80), nullable=False), sa.Column("title", sa.String(length=240), nullable=False), sa.Column("description", sa.Text()), sa.Column("trade_category", sa.String(length=100)),
        sa.Column("planned_start_date", sa.Date()), sa.Column("planned_completion_date", sa.Date()), sa.Column("budget_amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("selected_bid_id", sa.Integer()), sa.Column("award_approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")), sa.Column("award_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "package_code", name="uq_subcontract_package_project_code"),
    )
    for name, columns in (("ix_subcontract_packages_company_id", ["company_id"]), ("ix_subcontract_packages_branch_id", ["branch_id"]), ("ix_subcontract_packages_site_id", ["site_id"]), ("ix_subcontract_packages_project_id", ["project_id"]), ("ix_subcontract_packages_package_number", ["package_number"]), ("ix_subcontract_packages_status", ["status"])):
        op.create_index(name, "subcontract_packages", columns)

    op.create_table(
        "subcontract_package_lines",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("package_id", sa.Integer(), sa.ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False), sa.Column("description", sa.String(length=300), nullable=False), sa.Column("specification", sa.Text()), sa.Column("quantity", sa.Numeric(18, 3), nullable=False, server_default="1"), sa.Column("unit", sa.String(length=40), nullable=False, server_default="item"), sa.Column("budget_rate", sa.Numeric(18, 4), nullable=False, server_default="0"), sa.Column("budget_amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("milestone_id", sa.Integer(), sa.ForeignKey("project_milestones.id", ondelete="SET NULL")), sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("package_id", "line_number", name="uq_subcontract_package_line_number"),
    )
    op.create_index("ix_subcontract_package_lines_package_id", "subcontract_package_lines", ["package_id"])

    op.create_table(
        "subcontract_invitations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("package_id", sa.Integer(), sa.ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False), sa.Column("subcontractor_id", sa.Integer(), sa.ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False), sa.Column("invitation_number", sa.String(length=80), nullable=False), sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False), sa.Column("due_date", sa.Date()), sa.Column("status", sa.String(length=24), nullable=False, server_default="invited"), sa.Column("invitation_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("invited_by", sa.String(length=255), nullable=False), sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("package_id", "subcontractor_id", name="uq_subcontract_invitation_package_subcontractor"),
    )
    op.create_index("ix_subcontract_invitations_package_id", "subcontract_invitations", ["package_id"])
    op.create_index("ix_subcontract_invitations_subcontractor_id", "subcontract_invitations", ["subcontractor_id"])

    op.create_table(
        "subcontract_bids",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("package_id", sa.Integer(), sa.ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False), sa.Column("subcontractor_id", sa.Integer(), sa.ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False), sa.Column("bid_number", sa.String(length=80), nullable=False), sa.Column("bid_reference", sa.String(length=120), nullable=False), sa.Column("bid_date", sa.Date(), nullable=False), sa.Column("valid_until", sa.Date()), sa.Column("planned_duration_days", sa.Integer()), sa.Column("subtotal", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("tax_amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("total_amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(length=24), nullable=False, server_default="received"), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("exclusions", sa.Text()), sa.Column("submitted_by", sa.String(length=255), nullable=False), sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("package_id", "subcontractor_id", "bid_reference", name="uq_subcontract_bid_package_vendor_reference"),
    )
    for name, columns in (("ix_subcontract_bids_package_id", ["package_id"]), ("ix_subcontract_bids_subcontractor_id", ["subcontractor_id"]), ("ix_subcontract_bids_bid_number", ["bid_number"]), ("ix_subcontract_bids_status", ["status"])): op.create_index(name, "subcontract_bids", columns)
    op.create_foreign_key("fk_package_selected_bid", "subcontract_packages", "subcontract_bids", ["selected_bid_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "subcontract_bid_lines",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("bid_id", sa.Integer(), sa.ForeignKey("subcontract_bids.id", ondelete="CASCADE"), nullable=False), sa.Column("package_line_id", sa.Integer(), sa.ForeignKey("subcontract_package_lines.id", ondelete="RESTRICT"), nullable=False), sa.Column("quantity", sa.Numeric(18, 3), nullable=False), sa.Column("unit_rate", sa.Numeric(18, 4), nullable=False), sa.Column("line_total", sa.Numeric(18, 2), nullable=False), sa.Column("notes", sa.Text()), sa.UniqueConstraint("bid_id", "package_line_id", name="uq_subcontract_bid_package_line"),
    )
    op.create_index("ix_subcontract_bid_lines_bid_id", "subcontract_bid_lines", ["bid_id"])

    op.create_table(
        "subcontract_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("package_id", sa.Integer(), sa.ForeignKey("subcontract_packages.id", ondelete="CASCADE"), nullable=False), sa.Column("bid_id", sa.Integer(), sa.ForeignKey("subcontract_bids.id", ondelete="CASCADE"), nullable=False), sa.Column("technical_score", sa.Numeric(6, 2), nullable=False, server_default="0"), sa.Column("commercial_score", sa.Numeric(6, 2), nullable=False, server_default="0"), sa.Column("hse_score", sa.Numeric(6, 2), nullable=False, server_default="0"), sa.Column("programme_score", sa.Numeric(6, 2), nullable=False, server_default="0"), sa.Column("total_score", sa.Numeric(6, 2), nullable=False, server_default="0"), sa.Column("recommendation", sa.String(length=32), nullable=False, server_default="pending"), sa.Column("evaluation_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("notes", sa.Text()), sa.Column("evaluated_by", sa.String(length=255), nullable=False), sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("package_id", "bid_id", name="uq_subcontract_evaluation_package_bid"),
    )
    op.create_index("ix_subcontract_evaluations_package_id", "subcontract_evaluations", ["package_id"])
    op.create_index("ix_subcontract_evaluations_bid_id", "subcontract_evaluations", ["bid_id"])

    op.create_table(
        "subcontract_contracts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False), sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")), sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False), sa.Column("package_id", sa.Integer(), sa.ForeignKey("subcontract_packages.id", ondelete="RESTRICT"), nullable=False), sa.Column("subcontractor_id", sa.Integer(), sa.ForeignKey("subcontractors.id", ondelete="RESTRICT"), nullable=False), sa.Column("selected_bid_id", sa.Integer(), sa.ForeignKey("subcontract_bids.id", ondelete="SET NULL")), sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("contract_number", sa.String(length=80), nullable=False), sa.Column("title", sa.String(length=240), nullable=False), sa.Column("contract_reference", sa.String(length=160)), sa.Column("start_date", sa.Date(), nullable=False), sa.Column("completion_date", sa.Date(), nullable=False), sa.Column("currency", sa.String(length=8), nullable=False, server_default="LSL"), sa.Column("original_contract_sum", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("retention_pct", sa.Numeric(6, 3), nullable=False, server_default="5"), sa.Column("retention_cap", sa.Numeric(18, 2)), sa.Column("advance_amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("certified_amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("retention_held", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"), sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")), sa.Column("contract_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("approved_snapshot", sa.JSON()), sa.Column("notes", sa.Text()), sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("company_id", "contract_number", name="uq_subcontract_contract_company_number"), sa.UniqueConstraint("package_id", name="uq_subcontract_contract_package"),
    )
    for name, columns in (("ix_subcontract_contracts_company_id", ["company_id"]), ("ix_subcontract_contracts_branch_id", ["branch_id"]), ("ix_subcontract_contracts_site_id", ["site_id"]), ("ix_subcontract_contracts_project_id", ["project_id"]), ("ix_subcontract_contracts_package_id", ["package_id"]), ("ix_subcontract_contracts_subcontractor_id", ["subcontractor_id"]), ("ix_subcontract_contracts_contract_number", ["contract_number"]), ("ix_subcontract_contracts_status", ["status"])): op.create_index(name, "subcontract_contracts", columns)

    op.create_table(
        "subcontract_variations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("contract_id", sa.Integer(), sa.ForeignKey("subcontract_contracts.id", ondelete="CASCADE"), nullable=False), sa.Column("variation_number", sa.String(length=80), nullable=False), sa.Column("title", sa.String(length=240), nullable=False), sa.Column("reason", sa.Text(), nullable=False), sa.Column("value", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("time_extension_days", sa.Integer(), nullable=False, server_default="0"), sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"), sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("created_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("contract_id", "variation_number", name="uq_subcontract_variation_contract_number"),
    )
    op.create_index("ix_subcontract_variations_contract_id", "subcontract_variations", ["contract_id"]); op.create_index("ix_subcontract_variations_status", "subcontract_variations", ["status"])

    op.create_table(
        "subcontract_certificates",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("contract_id", sa.Integer(), sa.ForeignKey("subcontract_contracts.id", ondelete="CASCADE"), nullable=False), sa.Column("certificate_number", sa.String(length=80), nullable=False), sa.Column("certificate_type", sa.String(length=24), nullable=False, server_default="interim"), sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False), sa.Column("gross_value", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("previous_certified", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("cumulative_certified", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("retention_deduction", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("other_deductions", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("net_payable", sa.Numeric(18, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(length=24), nullable=False, server_default="draft"), sa.Column("approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")), sa.Column("evidence_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("approved_snapshot", sa.JSON()), sa.Column("notes", sa.Text()), sa.Column("prepared_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("approved_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("contract_id", "certificate_number", name="uq_subcontract_certificate_contract_number"),
    )
    op.create_index("ix_subcontract_certificates_contract_id", "subcontract_certificates", ["contract_id"]); op.create_index("ix_subcontract_certificates_period_end", "subcontract_certificates", ["period_end"]); op.create_index("ix_subcontract_certificates_status", "subcontract_certificates", ["status"])

    op.create_table(
        "subcontract_payments",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("certificate_id", sa.Integer(), sa.ForeignKey("subcontract_certificates.id", ondelete="RESTRICT"), nullable=False), sa.Column("payment_reference", sa.String(length=120), nullable=False), sa.Column("payment_date", sa.Date(), nullable=False), sa.Column("amount", sa.Numeric(18, 2), nullable=False), sa.Column("payment_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("notes", sa.Text()), sa.Column("recorded_by", sa.String(length=255), nullable=False), sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("company_id", "payment_reference", name="uq_subcontract_payment_reference"),
    )
    op.create_index("ix_subcontract_payments_certificate_id", "subcontract_payments", ["certificate_id"]); op.create_index("ix_subcontract_payments_payment_date", "subcontract_payments", ["payment_date"])

    op.create_table(
        "subcontract_performance_reviews",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False), sa.Column("contract_id", sa.Integer(), sa.ForeignKey("subcontract_contracts.id", ondelete="CASCADE"), nullable=False), sa.Column("review_date", sa.Date(), nullable=False), sa.Column("quality_score", sa.Numeric(4, 2), nullable=False), sa.Column("programme_score", sa.Numeric(4, 2), nullable=False), sa.Column("safety_score", sa.Numeric(4, 2), nullable=False), sa.Column("commercial_score", sa.Numeric(4, 2), nullable=False), sa.Column("overall_score", sa.Numeric(4, 2), nullable=False), sa.Column("status", sa.String(length=24), nullable=False, server_default="open"), sa.Column("improvement_action", sa.Text()), sa.Column("due_date", sa.Date()), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")), sa.Column("reviewed_by", sa.String(length=255), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("contract_id", "review_date", name="uq_subcontract_performance_review_day"),
    )
    op.create_index("ix_subcontract_performance_reviews_contract_id", "subcontract_performance_reviews", ["contract_id"]); op.create_index("ix_subcontract_performance_reviews_review_date", "subcontract_performance_reviews", ["review_date"]); op.create_index("ix_subcontract_performance_reviews_overall_score", "subcontract_performance_reviews", ["overall_score"])
    _audit_table()


def downgrade() -> None:
    for table in ("subcontract_audit_events", "subcontract_performance_reviews", "subcontract_payments", "subcontract_certificates", "subcontract_variations", "subcontract_contracts", "subcontract_evaluations", "subcontract_bid_lines"):
        op.drop_table(table)
    op.drop_constraint("fk_package_selected_bid", "subcontract_packages", type_="foreignkey")
    for table in ("subcontract_bids", "subcontract_invitations", "subcontract_package_lines", "subcontract_packages", "subcontractors"):
        op.drop_table(table)
