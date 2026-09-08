from fastapi import APIRouter, Depends

from app.api.v1.access import router as access_router
from app.api.v1.access_catalog import router as access_catalog_router
from app.api.v1.document_downloads import router as document_download_router
from app.api.v1.foundation import router as foundation_router
from app.api.v1.workforce import router as workforce_router
from app.api.v1.workforce_admin import router as workforce_admin_router
from app.api.v1.workforce_safe import router as workforce_safe_router
from app.api.v1.fleet import router as fleet_router
from app.api.v1.fleet_admin import router as fleet_admin_router
from app.api.v1.fleet_safe import router as fleet_safe_router
from app.api.v1.tenders import router as tender_router
from app.api.v1.tenders_admin import router as tender_admin_router
from app.api.v1.projects import router as project_router
from app.api.v1.projects_safe import router as project_safe_router
from app.api.v1.projects_reporting import router as project_reporting_router
from app.api.v1.projects_siteops_handoff import router as project_siteops_handoff_router
from app.api.v1.site_operations import router as site_operations_router
from app.api.v1.site_operations_control import router as site_operations_control_router
from app.api.v1.site_operations_safe import router as site_operations_safe_router
from app.api.v1.procurement import router as procurement_router
from app.api.v1.procurement_safe import router as procurement_safe_router
from app.api.v1.procurement_reporting import router as procurement_reporting_router
from app.api.v1.procurement_approval_safe import router as procurement_approval_safe_router
from app.api.v1.subcontracts import router as subcontract_router
from app.api.v1.subcontracts_safe import router as subcontract_safe_router
from app.api.v1.subcontracts_reporting import router as subcontract_reporting_router
from app.api.v1.subcontracts_approval_safe import router as subcontract_approval_safe_router
from app.api.v1.assistants import router as assistant_router
from app.api.v1.commercial import router as commercial_router
from app.api.v1.intelligence import router as intelligence_router
from app.api.v1.assurance import router as assurance_router
from app.api.v1.mobile import router as mobile_router
from app.api.v1.development import router as development_router
from app.api.v1.rollout import router as rollout_router
from app.api.v1.closeout import router as closeout_router
from app.api.v1.finance import router as finance_router
from app.api.v1.planning import router as planning_router
from app.api.v1.resources import router as resource_router
from app.api.v1.communications import router as communications_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.data_quality import router as data_quality_router
from app.api.v1.authority import router as authority_router
from app.api.v1.change_control import router as change_router
from app.api.v1.support import router as support_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.environment import router as environment_router
from app.api.v1.tools import router as tools_router
from app.api.v1.client_portal import router as client_portal_router
from app.api.v1.vendor_portal import router as vendor_portal_router
from app.api.v1.business_development import router as business_development_router
from app.api.v1.client_accounts import router as client_accounts_router
from app.api.v1.contract_control import router as contract_control_router
from app.api.v1.automation import router as automation_router
from app.security.access_guard import require_access_request_security
from app.security.phase1_guard import require_document_download_access, require_phase1_access
from app.security.workforce_guard import reconcile_workforce_access
from app.security.fleet_guard import reconcile_fleet_access

router = APIRouter()
router.include_router(access_router, dependencies=[Depends(require_access_request_security)])
router.include_router(access_catalog_router, dependencies=[Depends(require_access_request_security)])
router.include_router(foundation_router, dependencies=[Depends(require_phase1_access)])
router.include_router(document_download_router, dependencies=[Depends(require_document_download_access)])
workforce_dependencies = [Depends(require_access_request_security), Depends(reconcile_workforce_access)]
router.include_router(workforce_admin_router, dependencies=workforce_dependencies)
router.include_router(workforce_safe_router, dependencies=workforce_dependencies)
router.include_router(workforce_router, dependencies=workforce_dependencies)
fleet_dependencies = [Depends(require_access_request_security), Depends(reconcile_fleet_access)]
router.include_router(fleet_admin_router, dependencies=fleet_dependencies)
router.include_router(fleet_safe_router, dependencies=fleet_dependencies)
router.include_router(fleet_router, dependencies=fleet_dependencies)
tender_dependencies = [Depends(require_access_request_security)]
router.include_router(tender_admin_router, dependencies=tender_dependencies)
router.include_router(tender_router, dependencies=tender_dependencies)
project_dependencies = [Depends(require_access_request_security)]
router.include_router(project_siteops_handoff_router, dependencies=project_dependencies)
router.include_router(project_reporting_router, dependencies=project_dependencies)
router.include_router(project_safe_router, dependencies=project_dependencies)
router.include_router(project_router, dependencies=project_dependencies)
site_operations_dependencies = [Depends(require_access_request_security)]
router.include_router(site_operations_control_router, dependencies=site_operations_dependencies)
router.include_router(site_operations_safe_router, dependencies=site_operations_dependencies)
router.include_router(site_operations_router, dependencies=site_operations_dependencies)
procurement_dependencies = [Depends(require_access_request_security)]
router.include_router(procurement_reporting_router, dependencies=procurement_dependencies)
router.include_router(procurement_approval_safe_router, dependencies=procurement_dependencies)
router.include_router(procurement_safe_router, dependencies=procurement_dependencies)
router.include_router(procurement_router, dependencies=procurement_dependencies)
subcontract_dependencies = [Depends(require_access_request_security)]
router.include_router(subcontract_reporting_router, dependencies=subcontract_dependencies)
router.include_router(subcontract_approval_safe_router, dependencies=subcontract_dependencies)
router.include_router(subcontract_safe_router, dependencies=subcontract_dependencies)
router.include_router(subcontract_router, dependencies=subcontract_dependencies)
assistant_dependencies = [Depends(require_access_request_security)]
router.include_router(assistant_router, dependencies=assistant_dependencies)
commercial_dependencies = [Depends(require_access_request_security)]
router.include_router(commercial_router, dependencies=commercial_dependencies)
intelligence_dependencies = [Depends(require_access_request_security)]
router.include_router(intelligence_router, dependencies=intelligence_dependencies)
router.include_router(assurance_router, dependencies=[Depends(require_access_request_security)])
router.include_router(mobile_router, dependencies=[Depends(require_access_request_security)])
router.include_router(development_router, dependencies=[Depends(require_access_request_security)])
router.include_router(rollout_router, dependencies=[Depends(require_access_request_security)])
router.include_router(closeout_router, dependencies=[Depends(require_access_request_security)])
router.include_router(finance_router, dependencies=[Depends(require_access_request_security)])
router.include_router(planning_router, dependencies=[Depends(require_access_request_security)])
router.include_router(resource_router, dependencies=[Depends(require_access_request_security)])
router.include_router(communications_router, dependencies=[Depends(require_access_request_security)])
router.include_router(compliance_router, dependencies=[Depends(require_access_request_security)])
router.include_router(data_quality_router, dependencies=[Depends(require_access_request_security)])
router.include_router(authority_router, dependencies=[Depends(require_access_request_security)])
router.include_router(change_router, dependencies=[Depends(require_access_request_security)])
router.include_router(support_router, dependencies=[Depends(require_access_request_security)])
router.include_router(knowledge_router, dependencies=[Depends(require_access_request_security)])
router.include_router(environment_router, dependencies=[Depends(require_access_request_security)])
router.include_router(tools_router, dependencies=[Depends(require_access_request_security)])
router.include_router(client_portal_router, dependencies=[Depends(require_access_request_security)])
router.include_router(vendor_portal_router, dependencies=[Depends(require_access_request_security)])
router.include_router(business_development_router, dependencies=[Depends(require_access_request_security)])
router.include_router(client_accounts_router, dependencies=[Depends(require_access_request_security)])
router.include_router(contract_control_router, dependencies=[Depends(require_access_request_security)])
router.include_router(automation_router, dependencies=[Depends(require_access_request_security)])


@router.get("/overview", tags=["operations"])
def overview() -> dict[str, object]:
    """BuildTrack command-centre contract shared by every later phase."""
    return {
        "currency": "LSL",
        "currency_symbol": "M",
        "timezone": "Africa/Maseru",
        "phase_1": {"status": "operational", "capabilities": ["single_company_governance", "head_office_and_branches", "sites", "departments", "cost_centres", "roles_and_permissions", "approval_workflows", "audit_trail", "master_data", "number_sequences", "document_control"]},
        "phase_2": {"status": "operational", "capabilities": ["secure_login", "revocable_sessions", "password_policy_and_history", "account_lockout", "password_recovery", "user_lifecycle", "company_branch_site_role_assignments", "permission_enforcement", "session_management", "security_event_audit", "mandatory_password_change", "privilege_escalation_guard", "last_administrator_protection", "origin_validation"]},
        "phase_3": {"status": "operational", "capabilities": ["employee_master_records", "employment_contracts", "branch_site_workforce_scope", "leave_types_balances_and_approvals", "shifts_and_attendance", "timesheets_and_approval", "recurring_earnings_and_deductions", "payroll_periods_and_runs", "payroll_review_and_approval", "payroll_csv_export", "employee_csv_export", "employee_account_linking", "employee_lifecycle_control", "shift_assignment_administration", "signed_contract_activation", "payroll_period_close_control", "workforce_audit", "sensitive_field_permissions", "self_approval_controls", "workforce_role_reconciliation", "field_safe_user_and_pay_data"]},
        "phase_4": {"status": "operational", "capabilities": ["fleet_and_plant_register", "branch_site_operator_assignments", "odometer_and_engine_hour_history", "licence_insurance_and_compliance_expiry", "pre_start_and_periodic_inspections", "defect_and_serviceability_control", "fuel_transactions_and_costs", "preventive_maintenance_plans", "repair_jobs_and_downtime", "maintenance_maker_checker_approval", "fleet_alerts_and_due_service", "fleet_cost_dashboard_and_export", "fleet_control_queues_and_policy", "fleet_audit_history"]},
        "phase_5": {"status": "operational", "capabilities": ["tender_register_and_deadlines", "bid_no_bid_control", "tender_team_assignments", "document_compliance_checklist", "boq_estimating_and_pricing", "commercial_margin_control", "tender_securities", "clarifications", "shared_approval_workflows", "controlled_submission_tracking", "award_loss_analysis", "pipeline_dashboard_and_alerts", "tender_csv_export", "tender_audit_history", "phase6_mobilisation_handoff"]},
        "phase_6": {"status": "operational", "capabilities": ["awarded_tender_project_conversion", "project_site_and_cost_centre_creation", "project_team_mobilisation", "versioned_budget_baselines", "budget_maker_checker_approval", "baseline_programme_and_milestones", "mobilisation_readiness_checklist", "fleet_and_plant_project_allocations", "mobilisation_risk_register", "controlled_document_handover", "readiness_maker_checker_approval", "immutable_readiness_snapshot", "project_mobilisation_dashboard_and_alerts", "project_csv_export", "project_audit_history", "phase7_site_operations_handoff"]},
        "phase_7": {"status": "operational", "capabilities": ["approved_project_site_activation", "daily_site_diaries", "labour_deployment_evidence", "project_plant_usage", "material_receipt_usage_return_and_waste_evidence", "measured_progress_updates", "photo_and_document_evidence", "site_incident_and_corrective_action_control", "quality_inspections_and_nonconformances", "daily_report_maker_checker_approval", "mandatory_daily_report_approval", "critical_incident_policy_floor", "active_worker_guard", "immutable_approved_daily_report_snapshots", "site_operations_dashboard_and_alerts", "site_operations_control_queue", "approved_daily_report_csv_export", "site_operations_audit_history"]},
        "phase_8": {"status": "operational", "capabilities": ["supplier_register", "branch_site_store_locations", "stock_item_master", "weighted_average_stock_balances", "requisitions_and_maker_checker_approval", "supplier_quotations_and_comparison", "quotation_count_and_value_policy", "purchase_orders_and_maker_checker_approval", "goods_receipts_and_rejections", "immutable_stock_movements", "site_stock_issues_and_returns", "phase7_material_evidence_link", "branch_site_stock_transfers", "controlled_stock_adjustments", "negative_stock_prevention", "reorder_and_overdue_delivery_alerts", "procurement_commitment_dashboard", "stock_and_purchase_order_csv_exports", "procurement_audit_history"]},
        "phase_9": {"status": "operational", "capabilities": ["subcontractor_prequalification", "project_subcontract_packages", "scope_lines_and_bid_invitations", "controlled_bid_evaluation_and_award", "maker_checker_contract_approval", "approved_variations", "work_certificates_and_retention", "payment_evidence_and_overpayment_guard", "performance_reviews", "subcontract_dashboards_alerts_exports_and_audit"]},
        "phase_10": {"status": "operational", "capabilities": ["deterministic_purchase_request_review", "rule_based_category_suggestion", "quotation_document_extraction_and_comparison", "purchase_order_draft_preparation", "supplier_history_questions", "procurement_policy_answers", "tender_document_compliance_extraction", "tender_summary_and_checklist_generation", "tender_question_evidence", "controlled_tender_draft_templates", "30_14_7_1_day_reminder_feed", "immutable_assistant_analysis_history", "no_ai_model_dependency"]},
        "phase_11": {"status": "operational", "capabilities": ["client_contract_register", "budget_vs_actual_and_commitments", "immutable_project_cost_transactions", "client_variations_maker_checker", "client_valuations_and_invoices", "payment_receipt_evidence", "claims_and_deadline_control", "project_cash_flow_forecasting", "profitability_dashboard_alerts_exports_and_audit"]},
        "phase_12": {"status": "operational", "capabilities": ["director_dashboard", "branch_comparison", "project_health", "commercial_exposure", "tender_pipeline", "fleet_performance", "materials_reorder_intelligence", "exception_reports", "portfolio_export"]},
        "phase_13": {"status": "operational", "capabilities": ["controlled_project_document_revisions", "rfis_and_site_instructions", "permit_to_work", "toolbox_talks", "hse_inspections", "quality_nonconformances", "corrective_actions", "independent_assurance_review", "assurance_dashboard_and_audit"]},
        "phase_14": {"status": "operational", "capabilities": ["offline_phone_capture_queue", "idempotent_resynchronisation", "daily_diary_attendance_material_plant_photo_and_inspection_capture", "independent_mobile_evidence_review", "no_automatic_transaction_posting"]},
        "phase_15": {"status": "operational", "capabilities": ["recruitment_candidate_pipeline", "employee_onboarding_checklist", "licence_and_credential_register", "30_day_expiry_alerts", "training_plans_and_certification", "weighted_performance_reviews", "acknowledged_development_plans", "branch_and_site_scoped_hr_access"]},
        "phase_16": {"status": "operational", "capabilities": ["phased_branch_rollout_waves", "backup_and_recovery_evidence", "data_migration_reconciliation", "security_review_controls", "uat_sign_off", "user_training_and_support_readiness", "independent_go_live_review", "approved_branch_launch_gate", "rollout_audit_history"]},
        "phase_17": {"status": "operational", "capabilities": ["practical_completion_register", "controlled_handover_checklist", "final_account_and_retention_evidence", "defects_liability_register", "closeout_maker_checker_approval", "final_project_closure_gate", "closeout_dashboard_export_and_audit"]},
        "phase_18": {"status": "operational", "capabilities": ["financial_period_control", "chart_of_accounts", "balanced_journal_workflow", "supplier_invoice_register", "supplier_payment_request_and_evidence", "accounts_payable_and_receivable_dashboard", "maker_checker_finance_approval", "financial_export_and_audit"]},
        "phase_19": {"status": "operational", "capabilities": ["versioned_programme_baselines", "activity_dependencies_and_critical_path_visibility", "controlled_activity_progress_updates", "rolling_six_week_lookaheads", "delay_evidence_and_notice_alerts", "maker_checker_baseline_approval", "programme_dashboard_export_and_audit"]},
        "phase_20": {"status": "operational", "capabilities": ["versioned_resource_plans", "programme_activity_resource_demand", "employee_and_asset_capacity_conflict_detection", "material_resource_forecasting", "maker_checker_plan_and_request_approval", "fulfilment_evidence", "resource_dashboard_export_and_audit"]},
        "phase_21": {"status": "operational", "capabilities": ["project_stakeholder_register", "controlled_inbound_outbound_correspondence", "formal_correspondence_maker_checker_approval", "dispatch_and_response_evidence", "meeting_minutes_approval", "assigned_meeting_actions", "evidence_backed_action_verification", "communications_dashboard_export_and_audit"]},
        "phase_22": {"status": "operational", "capabilities": ["controlled_project_policy_register", "versioned_policy_approval", "source_referenced_compliance_obligations", "recurring_due_date_control", "evidence_backed_compliance_reviews", "maker_checker_review_approval", "compliance_alerts_export_and_audit"]},
        "phase_23": {"status": "operational", "capabilities": ["deterministic_project_data_quality_snapshot", "baseline_and_operational_evidence_checks", "overdue_control_detection", "source_activity_measurement", "evidence_backed_remediation", "independent_remediation_verification", "data_quality_dashboard_export_and_audit"]},
        "phase_24": {"status": "operational", "capabilities": ["effective_dated_delegated_authority_limits", "maloti_value_ranges", "role_branch_site_scope", "controlled_limit_evidence", "maker_checker_limit_approval", "approval_amount_evaluation", "authority_audit_history"]},
        "phase_25": {"status": "operational", "capabilities": ["controlled_change_register", "impact_and_limited_pilot_plans", "evidence_backed_change_submission", "independent_change_approval", "uat_and_release_evidence", "change_audit_history"]},
        "phase_26": {"status": "operational", "capabilities": ["branch_site_support_tickets", "priority_and_due_control", "resolution_evidence", "independent_ticket_verification", "support_audit_history"]},
        "phase_27": {"status": "operational", "capabilities": ["branch_site_operational_knowledge", "controlled_sop_evidence", "support_and_release_learning_links", "independent_article_publication", "review_due_control", "staff_acknowledgements", "knowledge_audit_history"]},
        "phase_28": {"status": "operational", "capabilities": ["project_environmental_plans", "controlled_waste_evidence", "hazardous_waste_verification", "environmental_inspections", "corrective_action_verification", "sustainability_dashboard", "environmental_audit_history"]},
        "phase_29": {"status": "operational", "capabilities": ["small_tool_register", "branch_site_tool_custody", "project_tool_issue_return", "calibration_certificate_control", "overdue_calibration_protection", "independent_calibration_verification", "tool_audit_history"]},
        "phase_30": {"status": "operational", "capabilities": ["client_share_pack_register", "approved_document_publication", "expiry_and_revocation", "opaque_token_links", "read_only_document_download", "external_sharing_audit_history"]},
        "phase_31": {"status": "operational", "capabilities": ["supplier_subcontractor_evidence_requests", "independent_portal_publication", "opaque_evidence_submission_links", "controlled_external_upload", "internal_evidence_verification", "vendor_portal_audit_history"]},
        "phase_32": {"status": "operational", "capabilities": ["branch_scoped_opportunity_register", "client_qualification", "activity_and_follow_up_control", "probability_weighted_pipeline", "controlled_tender_handoff", "business_development_audit_history"]},
        "phase_33": {"status": "operational", "capabilities": ["branch_scoped_client_accounts", "client_contacts", "supplied_feedback_register", "remediation_action_plans", "independent_feedback_verification", "client_account_audit_history"]},
        "phase_34": {"status": "operational", "capabilities": ["contract_notice_register", "notice_deadline_control", "extension_of_time_register", "independent_extension_review", "variation_instruction_register", "independent_instruction_approval", "contract_control_audit_history"]},
        "planned_operational_modules": [],
    }
