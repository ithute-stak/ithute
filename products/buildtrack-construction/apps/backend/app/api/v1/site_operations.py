from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.projects import approval_setting, assignment_authorised, issue_reference
from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStep,
    ApprovalWorkflow,
    CompanySetting,
    CostCentre,
    Document,
    Employee,
    FleetAsset,
    NumberSequence,
    Permission,
    Project,
    ProjectAssetAllocation,
    ProjectMilestone,
    ProjectReadinessSnapshot,
    ProjectSiteLink,
    Role,
    RolePermission,
    Site,
    SiteDailyReport,
    SiteEvidence,
    SiteIncident,
    SiteLabourEntry,
    SiteMaterialEntry,
    SiteOperationsActivation,
    SiteOperationsAuditEvent,
    SitePlantUsage,
    SiteProgressEntry,
    SiteQualityCheck,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/site-ops", tags=["Phase 7 - Site Operations"])
MONEY = Decimal("0.01")

SITEOPS_PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "siteops.view": ("site_operations", "view", "View site operations evidence"),
    "siteops.manage": ("site_operations", "manage", "Activate and administer site operations"),
    "siteops.diary": ("site_operations", "diary", "Create and maintain daily site reports"),
    "siteops.approve": ("site_operations", "approve", "Approve daily site reports"),
    "siteops.labour": ("site_operations", "labour", "Capture site labour deployment"),
    "siteops.plant": ("site_operations", "plant", "Capture project plant usage"),
    "siteops.materials": ("site_operations", "materials", "Capture site material movement evidence"),
    "siteops.progress": ("site_operations", "progress", "Capture measured site progress"),
    "siteops.incidents": ("site_operations", "incidents", "Capture and control site incidents"),
    "siteops.quality": ("site_operations", "quality", "Capture and control quality inspections and NCRs"),
    "siteops.export": ("site_operations", "export", "Export approved site operations evidence"),
}

ROLE_GRANTS: dict[str, set[str]] = {
    "SYSTEM_ADMIN": set(SITEOPS_PERMISSIONS),
    "HQ_EXECUTIVE": {"siteops.view", "siteops.approve", "siteops.export", "siteops.incidents", "siteops.quality"},
    "BRANCH_MANAGER": set(SITEOPS_PERMISSIONS),
    "SITE_MANAGER": {"siteops.view", "siteops.diary", "siteops.labour", "siteops.plant", "siteops.materials", "siteops.progress", "siteops.incidents", "siteops.quality", "siteops.export"},
    "APPROVER": {"siteops.view", "siteops.approve"},
    "AUDITOR": {"siteops.view", "siteops.export"},
    "PROJECT_MANAGER": {"siteops.view", "siteops.manage", "siteops.diary", "siteops.labour", "siteops.plant", "siteops.materials", "siteops.progress", "siteops.incidents", "siteops.quality", "siteops.export"},
    "SITE_SUPERVISOR": {"siteops.view", "siteops.diary", "siteops.labour", "siteops.plant", "siteops.materials", "siteops.progress", "siteops.incidents", "siteops.quality"},
    "HSE_OFFICER": {"siteops.view", "siteops.incidents", "siteops.export"},
    "QUALITY_OFFICER": {"siteops.view", "siteops.quality", "siteops.export"},
}

DEFAULT_POLICY = {
    "daily_report_lag_days": 1,
    "require_daily_report_approval": True,
    "serious_incident_severities": ["serious", "critical", "fatal"],
    "failed_quality_requires_action": True,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_dict(row: Any) -> dict[str, Any]:
    return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns}


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def commit(db: Session, detail: str = "Site operations record conflicts with existing data") -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from error


def require_anywhere(principal: Principal, permission: str) -> None:
    if not principal.has_permission_anywhere(permission):
        raise HTTPException(status_code=403, detail=f"Permission required: {permission}")


def require_scope(principal: Principal, permission: str, branch_id: int, site_id: int) -> None:
    if not principal.can(permission, branch_id=branch_id, site_id=site_id):
        raise HTTPException(status_code=403, detail=f"Permission required in this site: {permission}")


def policy(db: Session, company_id: int) -> dict[str, Any]:
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company_id, CompanySetting.key == "site_operations_policy"))
    value = row.value if row and isinstance(row.value, dict) else {}
    return {**DEFAULT_POLICY, **value}


def audit(db: Session, principal: Principal, action: str, entity_type: str, entity_id: int | str | None, *, project_id: int | None = None, site_id: int | None = None, detail: dict[str, Any] | None = None) -> None:
    db.add(SiteOperationsAuditEvent(
        company_id=principal.user.company_id,
        project_id=project_id,
        site_id=site_id,
        actor=principal.user.full_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        detail=detail or {},
    ))


def active_employee(db: Session, company_id: int, branch_id: int, employee_id: int | None) -> Employee | None:
    if employee_id is None:
        return None
    row = db.get(Employee, employee_id)
    if not row or row.company_id != company_id or row.branch_id != branch_id or row.employment_status not in {"active", "probation", "notice", "on_leave"}:
        raise HTTPException(status_code=422, detail="Employee is not active in the site branch")
    return row


def active_document(db: Session, company_id: int, document_id: int | None) -> Document | None:
    if document_id is None:
        return None
    row = db.get(Document, document_id)
    if not row or row.company_id != company_id or row.status != "active":
        raise HTTPException(status_code=422, detail="Document is not an active company document")
    return row


def activation_or_404(db: Session, principal: Principal, activation_id: int, permission: str = "siteops.view") -> SiteOperationsActivation:
    row = db.get(SiteOperationsActivation, activation_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Site operations activation not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def report_or_404(db: Session, principal: Principal, report_id: int, permission: str = "siteops.view") -> SiteDailyReport:
    row = db.get(SiteDailyReport, report_id)
    if not row or row.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Daily site report not found")
    require_scope(principal, permission, row.branch_id, row.site_id)
    return row


def editable(report: SiteDailyReport) -> None:
    if report.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail=f"Daily report is locked while {report.status}")


def create_approval(db: Session, principal: Principal, report: SiteDailyReport) -> ApprovalRequest:
    wf = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == report.company_id, ApprovalWorkflow.code == "SITE_DAILY_REPORT", ApprovalWorkflow.is_active.is_(True)))
    if not wf or not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == wf.id)):
        raise HTTPException(status_code=409, detail="Site daily report approval workflow is not configured")
    request = ApprovalRequest(
        company_id=report.company_id,
        workflow_id=wf.id,
        branch_id=report.branch_id,
        site_id=report.site_id,
        entity_type="site_daily_report",
        entity_id=str(report.id),
        reference=issue_reference(db, report.company_id, "APPROVAL", "APR"),
        title=f"Daily site report: {report.report_date.isoformat()} / {report.shift}",
        status="pending",
        current_step_order=1,
        requested_by=principal.user.full_name,
    )
    db.add(request); db.flush()
    return request


def report_snapshot(db: Session, report: SiteDailyReport) -> dict[str, Any]:
    labour = db.scalars(select(SiteLabourEntry).where(SiteLabourEntry.daily_report_id == report.id).order_by(SiteLabourEntry.id)).all()
    plant = db.scalars(select(SitePlantUsage).where(SitePlantUsage.daily_report_id == report.id).order_by(SitePlantUsage.id)).all()
    materials = db.scalars(select(SiteMaterialEntry).where(SiteMaterialEntry.daily_report_id == report.id).order_by(SiteMaterialEntry.id)).all()
    progress = db.scalars(select(SiteProgressEntry).where(SiteProgressEntry.daily_report_id == report.id).order_by(SiteProgressEntry.id)).all()
    evidence = db.scalars(select(SiteEvidence).where(SiteEvidence.daily_report_id == report.id).order_by(SiteEvidence.id)).all()
    incidents = db.scalars(select(SiteIncident).where(SiteIncident.daily_report_id == report.id).order_by(SiteIncident.id)).all()
    quality = db.scalars(select(SiteQualityCheck).where(SiteQualityCheck.daily_report_id == report.id).order_by(SiteQualityCheck.id)).all()
    return {
        "snapshot_schema": 1,
        "phase": 7,
        "captured_at": utcnow().isoformat(),
        "daily_report": row_dict(report),
        "labour": [row_dict(row) for row in labour],
        "plant": [row_dict(row) for row in plant],
        "materials": [row_dict(row) for row in materials],
        "progress": [row_dict(row) for row in progress],
        "evidence": [row_dict(row) for row in evidence],
        "incidents": [row_dict(row) for row in incidents],
        "quality": [row_dict(row) for row in quality],
        "totals": {
            "workers": sum(row.worker_count for row in labour),
            "labour_hours": str(sum((Decimal(row.regular_hours) + Decimal(row.overtime_hours)) * row.worker_count for row in labour)),
            "plant_hours": str(sum(Decimal(row.usage_hours) for row in plant)),
            "material_cost": str(money(sum((Decimal(row.total_cost) for row in materials), Decimal("0")))),
        },
    }


def submission_blockers(db: Session, report: SiteDailyReport) -> list[str]:
    blockers: list[str] = []
    counts = [
        db.scalar(select(func.count()).select_from(model).where(model.daily_report_id == report.id)) or 0
        for model in (SiteLabourEntry, SitePlantUsage, SiteMaterialEntry, SiteProgressEntry)
    ]
    if sum(counts) == 0 and not (report.no_work_reason or "").strip():
        blockers.append("Add site activity evidence or provide an explicit no-work reason")
    if sum(counts) > 0 and not (report.work_summary or "").strip():
        blockers.append("Work summary is required when site activity is recorded")
    serious = set(policy(db, report.company_id).get("serious_incident_severities", ["serious", "critical", "fatal"]))
    incidents = db.scalars(select(SiteIncident).where(SiteIncident.daily_report_id == report.id)).all()
    for incident in incidents:
        if incident.severity in serious and not (incident.immediate_action or "").strip():
            blockers.append(f"Incident {incident.incident_number} requires immediate action evidence")
    if bool(policy(db, report.company_id).get("failed_quality_requires_action", True)):
        failures = db.scalars(select(SiteQualityCheck).where(SiteQualityCheck.daily_report_id == report.id, SiteQualityCheck.result == "fail")).all()
        for check in failures:
            if not (check.corrective_action or "").strip():
                blockers.append(f"Quality failure {check.inspection_number} requires corrective action")
    return blockers


class SiteOpsPolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_report_lag_days: int = Field(default=1, ge=0, le=14)
    require_daily_report_approval: bool = True
    serious_incident_severities: list[Literal["minor", "moderate", "serious", "critical", "fatal"]] = Field(default_factory=lambda: ["serious", "critical", "fatal"], min_length=1)
    failed_quality_requires_action: bool = True


class ActivationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: int | None = None
    notes: str | None = None


class ActivationStatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "paused", "closed"]
    notes: str | None = None


class DailyReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_date: date
    shift: Literal["day", "night", "other"] = "day"
    weather_summary: str | None = Field(default=None, max_length=240)
    rain_hours: Decimal = Field(default=0, ge=0, le=24)
    work_summary: str | None = None
    planned_work: str | None = None
    blockers: str | None = None
    safety_summary: str | None = None
    visitor_summary: str | None = None
    no_work_reason: str | None = None


class LabourInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_id: int | None = None
    crew_name: str | None = Field(default=None, max_length=160)
    worker_count: int = Field(default=1, ge=1, le=500)
    regular_hours: Decimal = Field(default=0, ge=0, le=24)
    overtime_hours: Decimal = Field(default=0, ge=0, le=24)
    activity: str = Field(min_length=2, max_length=300)
    work_area: str | None = Field(default=None, max_length=200)
    cost_centre_id: int | None = None
    timesheet_entry_id: int | None = None
    notes: str | None = None


class PlantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: int
    operator_employee_id: int | None = None
    usage_hours: Decimal = Field(default=0, ge=0, le=24)
    idle_hours: Decimal = Field(default=0, ge=0, le=24)
    start_odometer_km: Decimal | None = Field(default=None, ge=0)
    end_odometer_km: Decimal | None = Field(default=None, ge=0)
    start_engine_hours: Decimal | None = Field(default=None, ge=0)
    end_engine_hours: Decimal | None = Field(default=None, ge=0)
    activity: str = Field(min_length=2, max_length=300)
    breakdown: bool = False
    notes: str | None = None


class MaterialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movement_type: Literal["received", "used", "returned", "waste"]
    material_code: str | None = Field(default=None, max_length=80)
    description: str = Field(min_length=2, max_length=300)
    unit: str = Field(min_length=1, max_length=40)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(default=0, ge=0)
    supplier_or_source: str | None = Field(default=None, max_length=240)
    source_reference: str | None = Field(default=None, max_length=160)
    work_area: str | None = Field(default=None, max_length=200)
    waste_reason: str | None = None
    document_id: int | None = None
    notes: str | None = None


class ProgressInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    milestone_id: int | None = None
    work_item: str = Field(min_length=2, max_length=300)
    unit: str | None = Field(default=None, max_length=40)
    planned_quantity: Decimal | None = Field(default=None, ge=0)
    period_quantity: Decimal | None = Field(default=None, ge=0)
    cumulative_quantity: Decimal | None = Field(default=None, ge=0)
    progress_pct: Decimal = Field(default=0, ge=0, le=100)
    measurement_date: date
    narrative: str | None = None
    document_id: int | None = None


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: int
    evidence_type: Literal["photo", "video", "drawing", "delivery_note", "measurement", "instruction", "other"] = "photo"
    caption: str | None = Field(default=None, max_length=300)
    work_area: str | None = Field(default=None, max_length=200)
    captured_at: datetime | None = None


class IncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_report_id: int | None = None
    incident_type: Literal["safety", "near_miss", "environment", "security", "equipment", "property", "other"]
    occurred_at: datetime
    severity: Literal["minor", "moderate", "serious", "critical", "fatal"]
    description: str = Field(min_length=2)
    employee_id: int | None = None
    persons_involved: str | None = None
    lost_time: bool = False
    immediate_action: str | None = None
    root_cause: str | None = None
    corrective_action: str | None = None
    owner_employee_id: int | None = None
    due_date: date | None = None
    status: Literal["open", "investigating", "action_required", "closed"] = "open"
    document_id: int | None = None


class IncidentUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root_cause: str | None = None
    corrective_action: str | None = None
    owner_employee_id: int | None = None
    due_date: date | None = None
    status: Literal["open", "investigating", "action_required", "closed"]
    document_id: int | None = None


class QualityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_report_id: int | None = None
    check_type: Literal["inspection", "test", "hold_point", "ncr", "snag", "handover", "other"]
    work_item: str = Field(min_length=2, max_length=300)
    specification_reference: str | None = Field(default=None, max_length=200)
    inspected_at: datetime
    inspector_employee_id: int | None = None
    result: Literal["pass", "conditional", "fail"]
    nonconformance_number: str | None = Field(default=None, max_length=100)
    corrective_action: str | None = None
    owner_employee_id: int | None = None
    due_date: date | None = None
    status: Literal["open", "action_required", "accepted", "closed"] = "open"
    document_id: int | None = None
    notes: str | None = None


class QualityUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    corrective_action: str | None = None
    owner_employee_id: int | None = None
    due_date: date | None = None
    status: Literal["open", "action_required", "accepted", "closed"]
    document_id: int | None = None
    notes: str | None = None


class ApprovalDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    comment: str | None = None


@router.get("/status")
def phase7_status(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    initialized = db.scalar(select(Permission.id).where(Permission.code == "siteops.view")) is not None
    if initialized:
        require_anywhere(principal, "siteops.view")
    elif not principal.has_company_permission("company.manage") and not principal.has_company_permission("projects.manage"):
        raise HTTPException(status_code=403, detail="Company/project administration permission is required to initialise Phase 7")
    return {"initialized": initialized, "phase": 7, "status": "operational" if initialized else "setup_required"}


@router.post("/bootstrap")
def bootstrap_phase7(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("company.manage") and not principal.has_company_permission("projects.manage"):
        raise HTTPException(status_code=403, detail="Company-level project administration is required to initialise Phase 7")
    permissions: dict[str, Permission] = {}
    for code, (module, action, description) in SITEOPS_PERMISSIONS.items():
        row = db.scalar(select(Permission).where(Permission.code == code))
        if not row:
            row = Permission(code=code, module=module, action=action, description=description); db.add(row); db.flush()
        permissions[code] = row
    roles = {row.code: row for row in db.scalars(select(Role).where(Role.company_id == principal.user.company_id)).all()}
    for code, name, scope, description in (
        ("SITE_SUPERVISOR", "Site Supervisor", "site", "Captures controlled daily site operations evidence"),
        ("HSE_OFFICER", "HSE Officer", "branch", "Controls site safety and environmental incident evidence"),
        ("QUALITY_OFFICER", "Quality Officer", "branch", "Controls site quality inspections and nonconformances"),
    ):
        if code not in roles:
            role = Role(company_id=principal.user.company_id, code=code, name=name, scope_level=scope, description=description, is_system=True, is_active=True); db.add(role); db.flush(); roles[code] = role
    for role_code, codes in ROLE_GRANTS.items():
        role = roles.get(role_code)
        if not role:
            continue
        existing = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        for code in codes:
            permission = permissions[code]
            if permission.id not in existing:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id)); existing.add(permission.id)
    for code, name, prefix in (("SITE_INCIDENT", "Site Incident Number", "INC"), ("SITE_QUALITY", "Site Quality Inspection Number", "QIN")):
        if not db.scalar(select(NumberSequence).where(NumberSequence.company_id == principal.user.company_id, NumberSequence.code == code)):
            db.add(NumberSequence(company_id=principal.user.company_id, code=code, name=name, prefix=prefix, next_number=1, padding=5, reset_period="yearly"))
    wf = db.scalar(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == principal.user.company_id, ApprovalWorkflow.code == "SITE_DAILY_REPORT"))
    if not wf:
        wf = ApprovalWorkflow(company_id=principal.user.company_id, code="SITE_DAILY_REPORT", name="Daily Site Report Approval", module="site_operations", description="Controlled maker/checker approval for site daily reports", min_amount=Decimal("0"), is_active=True); db.add(wf); db.flush()
    if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == wf.id)):
        branch_role, hq_role = roles.get("BRANCH_MANAGER"), roles.get("HQ_EXECUTIVE")
        if not branch_role or not hq_role:
            raise HTTPException(status_code=409, detail="Core Branch Manager and HQ Executive roles are required")
        db.add_all([
            ApprovalStep(workflow_id=wf.id, step_order=1, name="Branch Daily Report Review", role_id=branch_role.id, required_approvals=1, escalation_hours=24),
            ApprovalStep(workflow_id=wf.id, step_order=2, name="Head Office Daily Report Approval", role_id=hq_role.id, required_approvals=1, escalation_hours=48),
        ])
    setting = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "site_operations_policy"))
    if not setting:
        db.add(CompanySetting(company_id=principal.user.company_id, key="site_operations_policy", value=dict(DEFAULT_POLICY), description="Phase 7 site operations governance"))
    audit(db, principal, "siteops.phase7.bootstrap", "company", principal.user.company_id, detail={"permissions": len(SITEOPS_PERMISSIONS)})
    commit(db)
    return {"initialized": True, "phase": 7, "message": "Site Operations controls initialised"}


@router.get("/catalog")
def siteops_catalog(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "siteops.view")
    company_id = principal.user.company_id
    activations = [row for row in db.scalars(select(SiteOperationsActivation).where(SiteOperationsActivation.company_id == company_id).order_by(SiteOperationsActivation.id.desc())).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    projects = [row for row in db.scalars(select(Project).where(Project.company_id == company_id, Project.status.in_(["ready", "active"]))).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.primary_site_id)]
    employees = [row for row in db.scalars(select(Employee).where(Employee.company_id == company_id, Employee.employment_status.in_(["active", "probation", "notice", "on_leave"])).order_by(Employee.last_name, Employee.first_name)).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    documents = [row for row in db.scalars(select(Document).where(Document.company_id == company_id, Document.status == "active").order_by(Document.id.desc()).limit(500)).all() if row.branch_id is None or principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    allocations = db.scalars(select(ProjectAssetAllocation).where(ProjectAssetAllocation.company_id == company_id, ProjectAssetAllocation.status == "confirmed")).all()
    assets = []
    for allocation in allocations:
        project = db.get(Project, allocation.project_id); asset = db.get(FleetAsset, allocation.asset_id)
        if project and asset and principal.can("siteops.view", branch_id=project.branch_id, site_id=allocation.site_id):
            assets.append({"allocation_id": allocation.id, "project_id": allocation.project_id, "site_id": allocation.site_id, "asset_id": asset.id, "asset_number": asset.asset_number, "name": f"{asset.make} {asset.model}", "status": asset.status, "serviceability": asset.serviceability})
    return {
        "activations": [row_dict(row) for row in activations],
        "projects": [{"id": row.id, "project_number": row.project_number, "name": row.name, "branch_id": row.branch_id, "primary_site_id": row.primary_site_id, "cost_centre_id": row.cost_centre_id, "status": row.status} for row in projects],
        "employees": [{"id": row.id, "employee_number": row.employee_number, "branch_id": row.branch_id, "site_id": row.site_id, "name": f"{row.first_name} {row.last_name}", "job_title": row.job_title} for row in employees],
        "assets": assets,
        "documents": [{"id": row.id, "branch_id": row.branch_id, "site_id": row.site_id, "title": row.title, "category": row.category} for row in documents],
        "permissions": sorted(code for code in principal.permission_codes if code.startswith("siteops.")),
    }


@router.post("/activations/{project_id:int}", status_code=status.HTTP_201_CREATED)
def activate_site_operations(project_id: int, payload: ActivationInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project or project.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Project not found")
    site_id = payload.site_id or project.primary_site_id
    require_scope(principal, "siteops.manage", project.branch_id, site_id)
    if project.status not in {"ready", "active"} or project.readiness_status != "ready":
        raise HTTPException(status_code=409, detail="Project must have approved Phase 6 readiness before Site Operations can activate")
    snapshot = db.scalar(select(ProjectReadinessSnapshot).where(ProjectReadinessSnapshot.project_id == project.id).order_by(ProjectReadinessSnapshot.version.desc()).limit(1))
    if not snapshot:
        raise HTTPException(status_code=409, detail="Approved Phase 6 readiness snapshot is required")
    link = db.scalar(select(ProjectSiteLink).where(ProjectSiteLink.project_id == project.id, ProjectSiteLink.site_id == site_id))
    site = db.get(Site, site_id)
    if not link or not site or site.branch_id != project.branch_id:
        raise HTTPException(status_code=422, detail="Site must be linked to the project and belong to its branch")
    existing = db.scalar(select(SiteOperationsActivation).where(SiteOperationsActivation.project_id == project.id, SiteOperationsActivation.site_id == site_id))
    if existing:
        return row_dict(existing)
    row = SiteOperationsActivation(company_id=project.company_id, project_id=project.id, project_readiness_snapshot_id=snapshot.id, branch_id=project.branch_id, site_id=site_id, cost_centre_id=project.cost_centre_id, status="active", activated_by=principal.user.full_name, activated_at=utcnow(), notes=payload.notes)
    db.add(row); db.flush(); project.status = "active"
    audit(db, principal, "siteops.activated", "site_operations_activation", row.id, project_id=project.id, site_id=site_id, detail={"readiness_snapshot_id": snapshot.id})
    commit(db, "Site Operations is already activated for this project/site")
    return row_dict(row)


@router.post("/activations/{activation_id:int}/status")
def activation_status(activation_id: int, payload: ActivationStatusInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = activation_or_404(db, principal, activation_id, "siteops.manage")
    row.status = payload.status; row.notes = payload.notes if payload.notes is not None else row.notes
    if payload.status == "closed": row.closed_at = utcnow()
    elif row.closed_at is not None: row.closed_at = None
    audit(db, principal, f"siteops.activation.{payload.status}", "site_operations_activation", row.id, project_id=row.project_id, site_id=row.site_id)
    commit(db); return row_dict(row)


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), project_id: int | None = None, site_id: int | None = None, report_date: date | None = None) -> list[dict[str, Any]]:
    require_anywhere(principal, "siteops.view")
    query = select(SiteDailyReport).where(SiteDailyReport.company_id == principal.user.company_id)
    if project_id is not None: query = query.where(SiteDailyReport.project_id == project_id)
    if site_id is not None: query = query.where(SiteDailyReport.site_id == site_id)
    if report_date is not None: query = query.where(SiteDailyReport.report_date == report_date)
    rows = db.scalars(query.order_by(SiteDailyReport.report_date.desc(), SiteDailyReport.id.desc()).limit(500)).all()
    return [row_dict(row) for row in rows if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]


@router.post("/activations/{activation_id:int}/reports", status_code=status.HTTP_201_CREATED)
def create_report(activation_id: int, payload: DailyReportInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    activation = activation_or_404(db, principal, activation_id, "siteops.diary")
    if activation.status != "active": raise HTTPException(status_code=409, detail="Site Operations activation must be active")
    if payload.report_date > date.today(): raise HTTPException(status_code=422, detail="Daily site report cannot be dated in the future")
    row = SiteDailyReport(company_id=activation.company_id, activation_id=activation.id, project_id=activation.project_id, branch_id=activation.branch_id, site_id=activation.site_id, created_by=principal.user.full_name, created_at=utcnow(), updated_at=utcnow(), **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "siteops.report.created", "site_daily_report", row.id, project_id=row.project_id, site_id=row.site_id, detail={"date": row.report_date.isoformat(), "shift": row.shift}); commit(db, "A daily report already exists for this project/site/date/shift"); return row_dict(row)


@router.put("/reports/{report_id:int}")
def update_report(report_id: int, payload: DailyReportInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = report_or_404(db, principal, report_id, "siteops.diary"); editable(row)
    if payload.report_date > date.today(): raise HTTPException(status_code=422, detail="Daily site report cannot be dated in the future")
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.updated_at = utcnow(); audit(db, principal, "siteops.report.updated", "site_daily_report", row.id, project_id=row.project_id, site_id=row.site_id); commit(db, "A daily report already exists for this project/site/date/shift"); return row_dict(row)


@router.get("/reports/{report_id:int}")
def report_detail(report_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id)
    result = row_dict(report)
    result.update({
        "labour": [row_dict(row) for row in db.scalars(select(SiteLabourEntry).where(SiteLabourEntry.daily_report_id == report.id).order_by(SiteLabourEntry.id)).all()],
        "plant": [row_dict(row) for row in db.scalars(select(SitePlantUsage).where(SitePlantUsage.daily_report_id == report.id).order_by(SitePlantUsage.id)).all()],
        "materials": [row_dict(row) for row in db.scalars(select(SiteMaterialEntry).where(SiteMaterialEntry.daily_report_id == report.id).order_by(SiteMaterialEntry.id)).all()],
        "progress": [row_dict(row) for row in db.scalars(select(SiteProgressEntry).where(SiteProgressEntry.daily_report_id == report.id).order_by(SiteProgressEntry.id)).all()],
        "evidence": [row_dict(row) for row in db.scalars(select(SiteEvidence).where(SiteEvidence.daily_report_id == report.id).order_by(SiteEvidence.id)).all()],
        "incidents": [row_dict(row) for row in db.scalars(select(SiteIncident).where(SiteIncident.daily_report_id == report.id).order_by(SiteIncident.id)).all()],
        "quality": [row_dict(row) for row in db.scalars(select(SiteQualityCheck).where(SiteQualityCheck.daily_report_id == report.id).order_by(SiteQualityCheck.id)).all()],
        "submission_blockers": submission_blockers(db, report),
    })
    return result


@router.post("/reports/{report_id:int}/labour", status_code=201)
def add_labour(report_id: int, payload: LabourInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.labour"); editable(report)
    if payload.regular_hours + payload.overtime_hours > 24: raise HTTPException(status_code=422, detail="Regular plus overtime hours cannot exceed 24 hours per worker/day")
    employee = active_employee(db, report.company_id, report.branch_id, payload.employee_id)
    if employee and payload.worker_count != 1: raise HTTPException(status_code=422, detail="Individual employee labour entries must have worker_count = 1")
    if not employee and not (payload.crew_name or "").strip(): raise HTTPException(status_code=422, detail="Crew name is required when no employee is selected")
    if payload.cost_centre_id:
        centre = db.get(CostCentre, payload.cost_centre_id)
        if not centre or centre.company_id != report.company_id or (centre.branch_id is not None and centre.branch_id != report.branch_id): raise HTTPException(status_code=422, detail="Cost centre is outside this site branch")
    row = SiteLabourEntry(company_id=report.company_id, daily_report_id=report.id, project_id=report.project_id, site_id=report.site_id, recorded_by=principal.user.full_name, recorded_at=utcnow(), **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "siteops.labour.added", "site_labour_entry", row.id, project_id=report.project_id, site_id=report.site_id, detail={"worker_count": row.worker_count, "hours": str(Decimal(row.regular_hours)+Decimal(row.overtime_hours))}); commit(db); return row_dict(row)


@router.post("/reports/{report_id:int}/plant", status_code=201)
def add_plant(report_id: int, payload: PlantInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.plant"); editable(report)
    if payload.usage_hours + payload.idle_hours > 24: raise HTTPException(status_code=422, detail="Plant usage plus idle hours cannot exceed 24 hours/day")
    asset = db.get(FleetAsset, payload.asset_id)
    if not asset or asset.company_id != report.company_id or asset.status in {"out_of_service", "disposed"} or asset.serviceability == "unserviceable": raise HTTPException(status_code=422, detail="Plant asset is unavailable or unserviceable")
    allocation = db.scalar(select(ProjectAssetAllocation).where(ProjectAssetAllocation.project_id == report.project_id, ProjectAssetAllocation.site_id == report.site_id, ProjectAssetAllocation.asset_id == asset.id, ProjectAssetAllocation.status == "confirmed"))
    if not allocation: raise HTTPException(status_code=409, detail="Plant must have a confirmed Phase 6 allocation to this project/site")
    active_employee(db, report.company_id, report.branch_id, payload.operator_employee_id)
    if payload.start_odometer_km is not None and payload.end_odometer_km is not None and payload.end_odometer_km < payload.start_odometer_km: raise HTTPException(status_code=422, detail="End odometer cannot be below start odometer")
    if payload.start_engine_hours is not None and payload.end_engine_hours is not None and payload.end_engine_hours < payload.start_engine_hours: raise HTTPException(status_code=422, detail="End engine hours cannot be below start engine hours")
    row = SitePlantUsage(company_id=report.company_id, daily_report_id=report.id, project_id=report.project_id, site_id=report.site_id, recorded_by=principal.user.full_name, recorded_at=utcnow(), **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "siteops.plant.added", "site_plant_usage", row.id, project_id=report.project_id, site_id=report.site_id, detail={"asset_id": row.asset_id, "usage_hours": str(row.usage_hours), "breakdown": row.breakdown}); commit(db); return row_dict(row)


@router.post("/reports/{report_id:int}/materials", status_code=201)
def add_material(report_id: int, payload: MaterialInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.materials"); editable(report); active_document(db, report.company_id, payload.document_id)
    if payload.movement_type == "waste" and not (payload.waste_reason or "").strip(): raise HTTPException(status_code=422, detail="Waste movement requires a waste reason")
    values = payload.model_dump(); values["total_cost"] = money(payload.quantity * payload.unit_cost)
    row = SiteMaterialEntry(company_id=report.company_id, daily_report_id=report.id, project_id=report.project_id, site_id=report.site_id, recorded_by=principal.user.full_name, recorded_at=utcnow(), **values)
    db.add(row); db.flush(); audit(db, principal, "siteops.material.added", "site_material_entry", row.id, project_id=report.project_id, site_id=report.site_id, detail={"movement": row.movement_type, "quantity": str(row.quantity), "total_cost": str(row.total_cost)}); commit(db); return row_dict(row)


@router.post("/reports/{report_id:int}/progress", status_code=201)
def add_progress(report_id: int, payload: ProgressInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.progress"); editable(report); active_document(db, report.company_id, payload.document_id)
    if payload.milestone_id:
        milestone = db.get(ProjectMilestone, payload.milestone_id)
        if not milestone or milestone.project_id != report.project_id: raise HTTPException(status_code=422, detail="Milestone must belong to this project")
    if payload.cumulative_quantity is not None and payload.period_quantity is not None and payload.cumulative_quantity < payload.period_quantity: raise HTTPException(status_code=422, detail="Cumulative quantity cannot be below this period quantity")
    row = SiteProgressEntry(company_id=report.company_id, daily_report_id=report.id, project_id=report.project_id, site_id=report.site_id, recorded_by=principal.user.full_name, recorded_at=utcnow(), **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "siteops.progress.added", "site_progress_entry", row.id, project_id=report.project_id, site_id=report.site_id, detail={"progress_pct": str(row.progress_pct), "milestone_id": row.milestone_id}); commit(db); return row_dict(row)


@router.post("/reports/{report_id:int}/evidence", status_code=201)
def add_evidence(report_id: int, payload: EvidenceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.diary"); editable(report); active_document(db, report.company_id, payload.document_id)
    row = SiteEvidence(company_id=report.company_id, daily_report_id=report.id, project_id=report.project_id, site_id=report.site_id, added_by=principal.user.full_name, added_at=utcnow(), **payload.model_dump())
    db.add(row); db.flush(); audit(db, principal, "siteops.evidence.added", "site_evidence", row.id, project_id=report.project_id, site_id=report.site_id, detail={"document_id": row.document_id, "type": row.evidence_type}); commit(db, "This document is already linked as the same evidence type"); return row_dict(row)


@router.delete("/entries/{entry_type}/{entry_id:int}", status_code=204)
def delete_draft_entry(entry_type: Literal["labour", "plant", "materials", "progress", "evidence"], entry_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> None:
    mapping = {"labour": (SiteLabourEntry, "siteops.labour"), "plant": (SitePlantUsage, "siteops.plant"), "materials": (SiteMaterialEntry, "siteops.materials"), "progress": (SiteProgressEntry, "siteops.progress"), "evidence": (SiteEvidence, "siteops.diary")}
    model, permission = mapping[entry_type]; row = db.get(model, entry_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Site entry not found")
    report = report_or_404(db, principal, row.daily_report_id, permission); editable(report)
    db.delete(row); audit(db, principal, f"siteops.{entry_type}.deleted", model.__tablename__, entry_id, project_id=report.project_id, site_id=report.site_id); commit(db)


@router.post("/activations/{activation_id:int}/incidents", status_code=201)
def add_incident(activation_id: int, payload: IncidentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    activation = activation_or_404(db, principal, activation_id, "siteops.incidents")
    if payload.daily_report_id:
        report = report_or_404(db, principal, payload.daily_report_id, "siteops.incidents")
        if report.activation_id != activation.id: raise HTTPException(status_code=422, detail="Daily report belongs to another site activation")
    active_employee(db, activation.company_id, activation.branch_id, payload.employee_id); active_employee(db, activation.company_id, activation.branch_id, payload.owner_employee_id); active_document(db, activation.company_id, payload.document_id)
    serious = set(policy(db, activation.company_id).get("serious_incident_severities", ["serious", "critical", "fatal"]))
    if payload.severity in serious and not (payload.immediate_action or "").strip(): raise HTTPException(status_code=422, detail="Serious/critical/fatal incidents require immediate action evidence")
    values = payload.model_dump(); row = SiteIncident(company_id=activation.company_id, activation_id=activation.id, project_id=activation.project_id, branch_id=activation.branch_id, site_id=activation.site_id, incident_number=issue_reference(db, activation.company_id, "SITE_INCIDENT", "INC"), recorded_by=principal.user.full_name, recorded_at=utcnow(), **values)
    if row.status == "closed": row.closed_at = utcnow()
    db.add(row); db.flush(); audit(db, principal, "siteops.incident.created", "site_incident", row.id, project_id=row.project_id, site_id=row.site_id, detail={"incident_number": row.incident_number, "severity": row.severity}); commit(db); return row_dict(row)


@router.put("/incidents/{incident_id:int}")
def update_incident(incident_id: int, payload: IncidentUpdateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(SiteIncident, incident_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Site incident not found")
    require_scope(principal, "siteops.incidents", row.branch_id, row.site_id); active_employee(db, row.company_id, row.branch_id, payload.owner_employee_id); active_document(db, row.company_id, payload.document_id)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.closed_at = utcnow() if row.status == "closed" else None
    audit(db, principal, "siteops.incident.updated", "site_incident", row.id, project_id=row.project_id, site_id=row.site_id, detail={"status": row.status}); commit(db); return row_dict(row)


@router.post("/activations/{activation_id:int}/quality", status_code=201)
def add_quality(activation_id: int, payload: QualityInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    activation = activation_or_404(db, principal, activation_id, "siteops.quality")
    if payload.daily_report_id:
        report = report_or_404(db, principal, payload.daily_report_id, "siteops.quality")
        if report.activation_id != activation.id: raise HTTPException(status_code=422, detail="Daily report belongs to another site activation")
    active_employee(db, activation.company_id, activation.branch_id, payload.inspector_employee_id); active_employee(db, activation.company_id, activation.branch_id, payload.owner_employee_id); active_document(db, activation.company_id, payload.document_id)
    if payload.result == "fail" and bool(policy(db, activation.company_id).get("failed_quality_requires_action", True)) and not (payload.corrective_action or "").strip(): raise HTTPException(status_code=422, detail="Failed quality checks require corrective action")
    values = payload.model_dump(); row = SiteQualityCheck(company_id=activation.company_id, activation_id=activation.id, project_id=activation.project_id, branch_id=activation.branch_id, site_id=activation.site_id, inspection_number=issue_reference(db, activation.company_id, "SITE_QUALITY", "QIN"), created_by=principal.user.full_name, created_at=utcnow(), **values)
    if row.status == "closed": row.closed_at = utcnow()
    db.add(row); db.flush(); audit(db, principal, "siteops.quality.created", "site_quality_check", row.id, project_id=row.project_id, site_id=row.site_id, detail={"inspection_number": row.inspection_number, "result": row.result}); commit(db); return row_dict(row)


@router.put("/quality/{quality_id:int}")
def update_quality(quality_id: int, payload: QualityUpdateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    row = db.get(SiteQualityCheck, quality_id)
    if not row or row.company_id != principal.user.company_id: raise HTTPException(status_code=404, detail="Site quality check not found")
    require_scope(principal, "siteops.quality", row.branch_id, row.site_id); active_employee(db, row.company_id, row.branch_id, payload.owner_employee_id); active_document(db, row.company_id, payload.document_id)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    row.closed_at = utcnow() if row.status == "closed" else None
    audit(db, principal, "siteops.quality.updated", "site_quality_check", row.id, project_id=row.project_id, site_id=row.site_id, detail={"status": row.status}); commit(db); return row_dict(row)


@router.post("/reports/{report_id:int}/submit")
def submit_report(report_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.diary"); editable(report)
    blockers = submission_blockers(db, report)
    if blockers: raise HTTPException(status_code=409, detail={"message": "Daily report is not ready for approval", "blockers": blockers})
    if report.approval_request_id:
        existing = db.get(ApprovalRequest, report.approval_request_id)
        if existing and existing.status == "pending": return row_dict(existing)
    request = create_approval(db, principal, report)
    report.approval_request_id = request.id; report.status = "submitted"; report.submitted_by = principal.user.full_name; report.submitted_at = utcnow()
    audit(db, principal, "siteops.report.submitted", "approval_request", request.id, project_id=report.project_id, site_id=report.site_id, detail={"report_id": report.id, "date": report.report_date.isoformat()}); commit(db); return row_dict(request)


@router.post("/approvals/{request_id:int}/decision")
def decide_report(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type != "site_daily_report": raise HTTPException(status_code=404, detail="Site daily report approval request not found")
    report = report_or_404(db, principal, int(request.entity_id), "siteops.approve")
    project = db.get(Project, report.project_id)
    if not project: raise HTTPException(status_code=404, detail="Project not found")
    if request.status != "pending": raise HTTPException(status_code=409, detail=f"Approval request is already {request.status}")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step: raise HTTPException(status_code=409, detail="Current approval step is not configured")
    if not assignment_authorised(db, principal, step.role_id, project): raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not bool(approval_setting(db, report.company_id).get("allow_self_approval", False)): raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    if payload.decision == "approve":
        blockers = submission_blockers(db, report)
        if blockers: raise HTTPException(status_code=409, detail={"message": "Daily report no longer satisfies approval controls", "blockers": blockers})
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status = "rejected"; request.completed_at = utcnow(); report.status = "rejected"
    else:
        approved_count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved_count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step: request.current_step_order = next_step.step_order
            else:
                request.status = "approved"; request.completed_at = utcnow(); report.status = "approved"; report.approved_by = principal.user.full_name; report.approved_at = utcnow(); report.approved_snapshot = report_snapshot(db, report)
    audit(db, principal, f"siteops.report.approval.{payload.decision}", "approval_request", request.id, project_id=report.project_id, site_id=report.site_id, detail={"status": request.status, "step": step.step_order}); commit(db); return row_dict(request)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "siteops.view")
    activations = [row for row in db.scalars(select(SiteOperationsActivation).where(SiteOperationsActivation.company_id == principal.user.company_id)).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    activation_ids = {row.id for row in activations}; report_rows = db.scalars(select(SiteDailyReport).where(SiteDailyReport.activation_id.in_(activation_ids))).all() if activation_ids else []
    report_ids = {row.id for row in report_rows if row.status == "approved"}
    labour = db.scalars(select(SiteLabourEntry).where(SiteLabourEntry.daily_report_id.in_(report_ids))).all() if report_ids else []
    plant = db.scalars(select(SitePlantUsage).where(SitePlantUsage.daily_report_id.in_(report_ids))).all() if report_ids else []
    materials = db.scalars(select(SiteMaterialEntry).where(SiteMaterialEntry.daily_report_id.in_(report_ids))).all() if report_ids else []
    incidents = [row for row in db.scalars(select(SiteIncident).where(SiteIncident.activation_id.in_(activation_ids))).all()] if activation_ids else []
    quality = [row for row in db.scalars(select(SiteQualityCheck).where(SiteQualityCheck.activation_id.in_(activation_ids))).all()] if activation_ids else []
    return {
        "active_sites": sum(row.status == "active" for row in activations),
        "approved_reports": sum(row.status == "approved" for row in report_rows),
        "reports_pending": sum(row.status == "submitted" for row in report_rows),
        "approved_labour_hours": str(sum((Decimal(row.regular_hours) + Decimal(row.overtime_hours)) * row.worker_count for row in labour)),
        "approved_plant_hours": str(sum(Decimal(row.usage_hours) for row in plant)),
        "approved_material_cost": str(money(sum((Decimal(row.total_cost) for row in materials), Decimal("0")))),
        "open_incidents": sum(row.status != "closed" for row in incidents),
        "open_quality_actions": sum(row.status not in {"accepted", "closed"} and row.result in {"fail", "conditional"} for row in quality),
    }


@router.get("/dashboard/alerts")
def dashboard_alerts(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> list[dict[str, Any]]:
    require_anywhere(principal, "siteops.view")
    result: list[dict[str, Any]] = []; today = date.today(); lag = int(policy(db, principal.user.company_id).get("daily_report_lag_days", 1)); expected_day = today - timedelta(days=max(lag, 1))
    activations = [row for row in db.scalars(select(SiteOperationsActivation).where(SiteOperationsActivation.company_id == principal.user.company_id, SiteOperationsActivation.status == "active")).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    for activation in activations:
        report = db.scalar(select(SiteDailyReport).where(SiteDailyReport.activation_id == activation.id, SiteDailyReport.report_date == expected_day))
        if not report: result.append({"severity":"warning","type":"missing_daily_report","project_id":activation.project_id,"site_id":activation.site_id,"message":f"No daily report recorded for {expected_day.isoformat()}"})
    reports = [row for row in db.scalars(select(SiteDailyReport).where(SiteDailyReport.company_id == principal.user.company_id, SiteDailyReport.status == "submitted")).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    for report in reports:
        if report.submitted_at and report.submitted_at < utcnow() - timedelta(days=1): result.append({"severity":"warning","type":"approval_delay","project_id":report.project_id,"site_id":report.site_id,"report_id":report.id,"message":"Daily report approval has been pending for more than 24 hours"})
    incidents = [row for row in db.scalars(select(SiteIncident).where(SiteIncident.company_id == principal.user.company_id, SiteIncident.status != "closed")).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    for row in incidents:
        if row.severity in {"serious","critical","fatal"}: result.append({"severity":"critical","type":"incident","project_id":row.project_id,"site_id":row.site_id,"entity_id":row.id,"message":f"{row.incident_number}: {row.severity} incident remains {row.status}"})
        elif row.due_date and row.due_date < today: result.append({"severity":"warning","type":"incident_action_overdue","project_id":row.project_id,"site_id":row.site_id,"entity_id":row.id,"message":f"{row.incident_number} corrective action is overdue"})
    checks = [row for row in db.scalars(select(SiteQualityCheck).where(SiteQualityCheck.company_id == principal.user.company_id, SiteQualityCheck.status.not_in(["accepted","closed"]))).all() if principal.can("siteops.view", branch_id=row.branch_id, site_id=row.site_id)]
    for row in checks:
        if row.result == "fail": result.append({"severity":"warning","type":"quality_failure","project_id":row.project_id,"site_id":row.site_id,"entity_id":row.id,"message":f"{row.inspection_number}: failed quality check remains {row.status}"})
        if row.due_date and row.due_date < today: result.append({"severity":"warning","type":"quality_action_overdue","project_id":row.project_id,"site_id":row.site_id,"entity_id":row.id,"message":f"{row.inspection_number} corrective action is overdue"})
    return result


@router.get("/policy/current")
def get_policy(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    require_anywhere(principal, "siteops.view"); value = policy(db, principal.user.company_id); return {**value, "can_edit": principal.has_company_permission("siteops.manage") or principal.has_company_permission("company.manage")}


@router.put("/policy/current")
def set_policy(payload: SiteOpsPolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("siteops.manage") and not principal.has_company_permission("company.manage"): raise HTTPException(status_code=403, detail="Company-level Site Operations administration is required")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "site_operations_policy")); value = payload.model_dump(mode="json")
    if row: row.value = value
    else: db.add(CompanySetting(company_id=principal.user.company_id, key="site_operations_policy", value=value, description="Phase 7 site operations governance"))
    commit(db); return {**value, "can_edit": True}


@router.get("/exports/daily-reports.csv")
def export_daily_reports(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> StreamingResponse:
    require_anywhere(principal, "siteops.export"); output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Report ID","Project ID","Site ID","Date","Shift","Status","Work Summary","Workers","Labour Hours","Plant Hours","Material Cost","Approved By","Approved At"])
    rows = db.scalars(select(SiteDailyReport).where(SiteDailyReport.company_id == principal.user.company_id, SiteDailyReport.status == "approved").order_by(SiteDailyReport.report_date.desc())).all()
    for report in rows:
        if not principal.can("siteops.export", branch_id=report.branch_id, site_id=report.site_id): continue
        snapshot = report.approved_snapshot if isinstance(report.approved_snapshot, dict) else {}; totals = snapshot.get("totals", {}) if isinstance(snapshot.get("totals", {}), dict) else {}
        writer.writerow([report.id,report.project_id,report.site_id,report.report_date.isoformat(),report.shift,report.status,report.work_summary or "",totals.get("workers",0),totals.get("labour_hours","0"),totals.get("plant_hours","0"),totals.get("material_cost","0.00"),report.approved_by or "",report.approved_at.isoformat() if report.approved_at else ""])
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8-sig")), media_type="text/csv; charset=utf-8", headers={"Content-Disposition":"attachment; filename=buildtrack-site-daily-reports.csv"})


@router.get("/audit/events")
def audit_events(db: Session = Depends(get_db), principal: Principal = Depends(current_principal), limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    require_anywhere(principal, "siteops.view")
    rows = db.scalars(select(SiteOperationsAuditEvent).where(SiteOperationsAuditEvent.company_id == principal.user.company_id).order_by(SiteOperationsAuditEvent.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows if row.site_id is None or any(principal.can("siteops.view", branch_id=activation.branch_id, site_id=row.site_id) for activation in db.scalars(select(SiteOperationsActivation).where(SiteOperationsActivation.site_id == row.site_id, SiteOperationsActivation.company_id == principal.user.company_id)).all())]
