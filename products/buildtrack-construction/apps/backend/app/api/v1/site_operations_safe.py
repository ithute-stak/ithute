from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.site_operations import (
    EvidenceInput,
    IncidentInput,
    IncidentUpdateInput,
    LabourInput,
    MaterialInput,
    PlantInput,
    ProgressInput,
    QualityInput,
    QualityUpdateInput,
    SiteOpsPolicyInput,
    activation_or_404,
    add_evidence as base_add_evidence,
    add_incident as base_add_incident,
    add_labour as base_add_labour,
    add_material as base_add_material,
    add_plant as base_add_plant,
    add_progress as base_add_progress,
    add_quality as base_add_quality,
    commit,
    policy,
    report_or_404,
    update_incident as base_update_incident,
    update_quality as base_update_quality,
)
from app.db.session import get_db
from app.models import CompanySetting, Document, Employee, SiteIncident, SiteQualityCheck, TimesheetEntry
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/site-ops", tags=["Phase 7 - Site Operations Safety"])


def _active_site_worker(db: Session, principal: Principal, employee_id: int | None) -> None:
    if employee_id is None:
        return
    employee = db.get(Employee, employee_id)
    if not employee or employee.company_id != principal.user.company_id:
        raise HTTPException(status_code=422, detail="Employee does not belong to the active company")
    if employee.employment_status not in {"active", "probation", "notice"}:
        raise HTTPException(status_code=422, detail="Employee must be actively available for site work; employees on leave or inactive cannot be recorded as working")


def _document_in_site_scope(db: Session, principal: Principal, document_id: int | None, branch_id: int, site_id: int) -> None:
    if document_id is None:
        return
    document = db.get(Document, document_id)
    if not document or document.company_id != principal.user.company_id or document.status != "active":
        raise HTTPException(status_code=422, detail="Document is not an active company document")
    if document.branch_id is not None and document.branch_id != branch_id:
        raise HTTPException(status_code=422, detail="Document belongs to another branch")
    if document.site_id is not None and document.site_id != site_id:
        raise HTTPException(status_code=422, detail="Document belongs to another site")


@router.post("/reports/{report_id:int}/labour", status_code=status.HTTP_201_CREATED)
def add_labour_safe(report_id: int, payload: LabourInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.labour")
    _active_site_worker(db, principal, payload.employee_id)
    if payload.timesheet_entry_id is not None:
        if payload.employee_id is None:
            raise HTTPException(status_code=422, detail="A payroll timesheet reference can only be linked to an individual employee labour entry")
        timesheet = db.get(TimesheetEntry, payload.timesheet_entry_id)
        if not timesheet or timesheet.company_id != report.company_id:
            raise HTTPException(status_code=422, detail="Timesheet does not belong to the active company")
        if timesheet.employee_id != payload.employee_id or timesheet.branch_id != report.branch_id or timesheet.site_id != report.site_id or timesheet.work_date != report.report_date:
            raise HTTPException(status_code=422, detail="Timesheet must belong to the same employee, branch, site and report date")
        if timesheet.status != "approved":
            raise HTTPException(status_code=409, detail="Only an approved Phase 3 timesheet may be referenced by approved site labour evidence")
    return base_add_labour(report_id=report_id, payload=payload, db=db, principal=principal)


@router.post("/reports/{report_id:int}/plant", status_code=status.HTTP_201_CREATED)
def add_plant_safe(report_id: int, payload: PlantInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    _active_site_worker(db, principal, payload.operator_employee_id)
    return base_add_plant(report_id=report_id, payload=payload, db=db, principal=principal)


@router.post("/reports/{report_id:int}/materials", status_code=status.HTTP_201_CREATED)
def add_material_safe(report_id: int, payload: MaterialInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.materials")
    _document_in_site_scope(db, principal, payload.document_id, report.branch_id, report.site_id)
    return base_add_material(report_id=report_id, payload=payload, db=db, principal=principal)


@router.post("/reports/{report_id:int}/progress", status_code=status.HTTP_201_CREATED)
def add_progress_safe(report_id: int, payload: ProgressInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.progress")
    _document_in_site_scope(db, principal, payload.document_id, report.branch_id, report.site_id)
    return base_add_progress(report_id=report_id, payload=payload, db=db, principal=principal)


@router.post("/reports/{report_id:int}/evidence", status_code=status.HTTP_201_CREATED)
def add_evidence_safe(report_id: int, payload: EvidenceInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    report = report_or_404(db, principal, report_id, "siteops.diary")
    _document_in_site_scope(db, principal, payload.document_id, report.branch_id, report.site_id)
    return base_add_evidence(report_id=report_id, payload=payload, db=db, principal=principal)


@router.post("/activations/{activation_id:int}/incidents", status_code=status.HTTP_201_CREATED)
def add_incident_safe(activation_id: int, payload: IncidentInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    activation = activation_or_404(db, principal, activation_id, "siteops.incidents")
    _document_in_site_scope(db, principal, payload.document_id, activation.branch_id, activation.site_id)
    return base_add_incident(activation_id=activation_id, payload=payload, db=db, principal=principal)


@router.put("/incidents/{incident_id:int}")
def update_incident_safe(incident_id: int, payload: IncidentUpdateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    incident = db.get(SiteIncident, incident_id)
    if not incident or incident.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Site incident not found")
    _document_in_site_scope(db, principal, payload.document_id, incident.branch_id, incident.site_id)
    return base_update_incident(incident_id=incident_id, payload=payload, db=db, principal=principal)


@router.post("/activations/{activation_id:int}/quality", status_code=status.HTTP_201_CREATED)
def add_quality_safe(activation_id: int, payload: QualityInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    activation = activation_or_404(db, principal, activation_id, "siteops.quality")
    _document_in_site_scope(db, principal, payload.document_id, activation.branch_id, activation.site_id)
    return base_add_quality(activation_id=activation_id, payload=payload, db=db, principal=principal)


@router.put("/quality/{quality_id:int}")
def update_quality_safe(quality_id: int, payload: QualityUpdateInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    quality = db.get(SiteQualityCheck, quality_id)
    if not quality or quality.company_id != principal.user.company_id:
        raise HTTPException(status_code=404, detail="Site quality check not found")
    _document_in_site_scope(db, principal, payload.document_id, quality.branch_id, quality.site_id)
    return base_update_quality(quality_id=quality_id, payload=payload, db=db, principal=principal)


@router.get("/policy/current")
def get_policy_safe(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_permission_anywhere("siteops.view"):
        raise HTTPException(status_code=403, detail="Permission required: siteops.view")
    value = policy(db, principal.user.company_id)
    serious = set(str(item) for item in value.get("serious_incident_severities", [])) | {"critical", "fatal"}
    return {
        **value,
        "require_daily_report_approval": True,
        "serious_incident_severities": sorted(serious),
        "can_edit": principal.has_company_permission("siteops.manage") or principal.has_company_permission("company.manage"),
    }


@router.put("/policy/current")
def set_policy_safe(payload: SiteOpsPolicyInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_company_permission("siteops.manage") and not principal.has_company_permission("company.manage"):
        raise HTTPException(status_code=403, detail="Company-level Site Operations administration is required")
    serious = set(payload.serious_incident_severities) | {"critical", "fatal"}
    value = {
        "daily_report_lag_days": payload.daily_report_lag_days,
        "require_daily_report_approval": True,
        "serious_incident_severities": sorted(serious),
        "failed_quality_requires_action": payload.failed_quality_requires_action,
    }
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == principal.user.company_id, CompanySetting.key == "site_operations_policy"))
    if row:
        row.value = value
    else:
        db.add(CompanySetting(company_id=principal.user.company_id, key="site_operations_policy", value=value, description="Phase 7 site operations governance"))
    commit(db)
    return {**value, "can_edit": True}
