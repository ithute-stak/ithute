"""phase 5 tender management

Revision ID: 0006_phase5_tender_management
Revises: 0005_phase4_fleet_plant
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_phase5_tender_management"
down_revision = "0005_phase4_fleet_plant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("cost_centre_id", sa.Integer(), sa.ForeignKey("cost_centres.id", ondelete="SET NULL")),
        sa.Column("lead_employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("tender_number", sa.String(80), nullable=False),
        sa.Column("external_reference", sa.String(160)),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("client_name", sa.String(240), nullable=False),
        sa.Column("client_contact", sa.String(240)),
        sa.Column("procurement_method", sa.String(100)),
        sa.Column("source", sa.String(120)),
        sa.Column("category", sa.String(120)),
        sa.Column("location", sa.String(240)),
        sa.Column("issue_date", sa.Date()),
        sa.Column("briefing_date", sa.DateTime(timezone=True)),
        sa.Column("site_visit_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("site_visit_date", sa.DateTime(timezone=True)),
        sa.Column("clarification_deadline", sa.DateTime(timezone=True)),
        sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opening_date", sa.DateTime(timezone=True)),
        sa.Column("validity_days", sa.Integer()),
        sa.Column("currency", sa.String(8), nullable=False, server_default="LSL"),
        sa.Column("estimated_contract_value", sa.Numeric(18, 2)),
        sa.Column("direct_cost_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("tender_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("gross_margin", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("gross_margin_pct", sa.Numeric(8, 3), nullable=False, server_default="0"),
        sa.Column("win_probability", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("priority", sa.String(24), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(32), nullable=False, server_default="identified"),
        sa.Column("bid_decision", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("bid_decision_reason", sa.Text()),
        sa.Column("bid_decided_by", sa.String(255)),
        sa.Column("bid_decided_at", sa.DateTime(timezone=True)),
        sa.Column("commercial_approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("submission_approval_request_id", sa.Integer(), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "tender_number", name="uq_tender_company_number"),
        sa.UniqueConstraint("company_id", "external_reference", name="uq_tender_company_external_reference"),
    )
    for c in ("company_id", "branch_id", "site_id", "cost_centre_id", "lead_employee_id", "client_name", "category", "submission_deadline", "priority", "status", "bid_decision", "commercial_approval_request_id", "submission_approval_request_id"):
        op.create_index(f"ix_tenders_{c}", "tenders", [c])

    op.create_table(
        "tender_team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(60), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("added_by", sa.String(255), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tender_id", "employee_id", "role", name="uq_tender_team_member_role"),
    )
    for c in ("company_id", "tender_id", "employee_id", "role"):
        op.create_index(f"ix_tender_team_members_{c}", "tender_team_members", [c])

    op.create_table(
        "tender_checklist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(24), nullable=False, server_default="missing"),
        sa.Column("owner_employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("due_date", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for c in ("company_id", "tender_id", "category", "status"):
        op.create_index(f"ix_tender_checklist_items_{c}", "tender_checklist_items", [c])

    op.create_table(
        "tender_estimate_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(160)),
        sa.Column("item_code", sa.String(80)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False, server_default="item"),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="1"),
        sa.Column("material_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("labour_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("plant_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("subcontract_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("other_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("direct_unit_cost", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("direct_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("markup_pct", sa.Numeric(8, 3), nullable=False, server_default="0"),
        sa.Column("selling_rate", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("selling_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for c in ("company_id", "tender_id", "section"):
        op.create_index(f"ix_tender_estimate_items_{c}", "tender_estimate_items", [c])

    op.create_table(
        "tender_securities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("security_type", sa.String(60), nullable=False),
        sa.Column("provider", sa.String(200)),
        sa.Column("reference_number", sa.String(160)),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("issue_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("status", sa.String(24), nullable=False, server_default="required"),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for c in ("company_id", "tender_id", "security_type", "expiry_date", "status"):
        op.create_index(f"ix_tender_securities_{c}", "tender_securities", [c])

    op.create_table(
        "tender_clarifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clarification_number", sa.String(80), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sent_to", sa.String(240)),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("response", sa.Text()),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("raised_by", sa.String(255), nullable=False),
    )
    for c in ("company_id", "tender_id", "clarification_number", "due_at", "status"):
        op.create_index(f"ix_tender_clarifications_{c}", "tender_clarifications", [c])

    op.create_table(
        "tender_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("submission_method", sa.String(60), nullable=False),
        sa.Column("submission_location", sa.String(300)),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_by", sa.String(255), nullable=False),
        sa.Column("acknowledgement_reference", sa.String(200)),
        sa.Column("acknowledgement_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("tender_price", sa.Numeric(18, 2), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("tender_id", "version", name="uq_tender_submission_version"),
    )
    for c in ("company_id", "tender_id"):
        op.create_index(f"ix_tender_submissions_{c}", "tender_submissions", [c])

    op.create_table(
        "tender_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("decision_date", sa.Date()),
        sa.Column("awarded_amount", sa.Numeric(18, 2)),
        sa.Column("winning_bidder", sa.String(240)),
        sa.Column("winning_amount", sa.Numeric(18, 2)),
        sa.Column("loss_reason", sa.Text()),
        sa.Column("lessons_learned", sa.Text()),
        sa.Column("award_document_id", sa.Integer(), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tender_id", name="uq_tender_outcome_tender"),
    )
    for c in ("company_id", "tender_id", "outcome"):
        op.create_index(f"ix_tender_outcomes_{c}", "tender_outcomes", [c])

    op.create_table(
        "tender_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tender_id", sa.Integer(), sa.ForeignKey("tenders.id", ondelete="SET NULL")),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id", ondelete="SET NULL")),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100)),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    for c in ("company_id", "tender_id", "branch_id", "action", "occurred_at"):
        op.create_index(f"ix_tender_audit_events_{c}", "tender_audit_events", [c])


def downgrade() -> None:
    for table in (
        "tender_audit_events",
        "tender_outcomes",
        "tender_submissions",
        "tender_clarifications",
        "tender_securities",
        "tender_estimate_items",
        "tender_checklist_items",
        "tender_team_members",
        "tenders",
    ):
        op.drop_table(table)
