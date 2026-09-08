from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.projects import (
    ApprovalDecisionInput,
    PROJECT_POLICY_DEFAULT,
    assignment_authorised,
    approval_setting,
    audit,
    bootstrap_phase6 as base_bootstrap,
    commit,
    create_approval,
    project_detail as base_project_detail,
    project_or_404,
    project_policy,
    row_dict,
    snapshot_payload,
    utcnow,
)
from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStep,
    Branch,
    Document,
    Employee,
    FleetAsset,
    Permission,
    Project,
    ProjectAssetAllocation,
    ProjectBudgetBaseline,
    ProjectHandoverDocument,
    ProjectMilestone,
    ProjectMobilisationItem,
    ProjectReadinessSnapshot,
    ProjectRisk,
    Role,
    RolePermission,
    Site,
    Tender,
)
from app.security.access import Principal, current_principal

router = APIRouter(prefix="/projects", tags=["Phase 6 - Project Mobilisation Control"])


def strict_readiness_state(db: Session, project: Project) -> dict[str, Any]:
    policy = project_policy(db, project.company_id)
    blockers: list[str] = []
    baseline = db.scalar(select(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id == project.id).order_by(ProjectBudgetBaseline.version.desc()).limit(1))
    if not baseline or baseline.status != "approved" or baseline.total_amount <= 0:
        blockers.append("Latest project budget baseline must be approved")
    milestones = db.scalars(select(ProjectMilestone).where(ProjectMilestone.project_id == project.id)).all()
    if not milestones:
        blockers.append("Baseline project programme requires at least one milestone")
    else:
        total_weight = sum((Decimal(item.weight_pct or 0) for item in milestones), Decimal("0"))
        required_weight = Decimal(str(policy.get("programme_weight_pct", PROJECT_POLICY_DEFAULT["programme_weight_pct"])))
        if abs(total_weight - required_weight) > Decimal("0.001"):
            blockers.append(f"Programme milestone weights must total {required_weight}% (currently {total_weight}%)")
    missing_mob = db.scalar(select(func.count()).select_from(ProjectMobilisationItem).where(ProjectMobilisationItem.project_id == project.id, ProjectMobilisationItem.required.is_(True), ProjectMobilisationItem.status != "ready")) or 0
    if missing_mob:
        blockers.append(f"{missing_mob} required mobilisation checklist item(s) are not ready")
    missing_docs = db.scalar(select(func.count()).select_from(ProjectHandoverDocument).where(ProjectHandoverDocument.project_id == project.id, ProjectHandoverDocument.required.is_(True), ProjectHandoverDocument.status != "verified")) or 0
    if missing_docs:
        blockers.append(f"{missing_docs} required handover document(s) are not verified")
    if not project.project_manager_employee_id:
        blockers.append("Project manager must be assigned")
    else:
        from app.models import ProjectTeamMember
        manager_team = db.scalar(select(ProjectTeamMember).where(ProjectTeamMember.project_id == project.id, ProjectTeamMember.employee_id == project.project_manager_employee_id, ProjectTeamMember.role == "project_manager", ProjectTeamMember.status != "released"))
        if not manager_team:
            blockers.append("Project manager must be present in the active project team")
    threshold = int(policy.get("critical_risk_threshold", PROJECT_POLICY_DEFAULT["critical_risk_threshold"]))
    critical = db.scalar(select(func.count()).select_from(ProjectRisk).where(ProjectRisk.project_id == project.id, ProjectRisk.rating >= threshold, ProjectRisk.status == "open")) or 0
    if critical:
        blockers.append(f"{critical} critical/open mobilisation risk(s) require mitigation")
    planned_assets = db.scalar(select(func.count()).select_from(ProjectAssetAllocation).where(ProjectAssetAllocation.project_id == project.id, ProjectAssetAllocation.status == "planned")) or 0
    if planned_assets:
        blockers.append(f"{planned_assets} planned fleet/plant allocation(s) are not confirmed")
    for allocation in db.scalars(select(ProjectAssetAllocation).where(ProjectAssetAllocation.project_id == project.id, ProjectAssetAllocation.status == "confirmed")).all():
        asset = db.get(FleetAsset, allocation.asset_id)
        if not asset or asset.serviceability == "unserviceable" or asset.status in {"out_of_service", "disposed"}:
            blockers.append(f"Allocated fleet/plant asset {allocation.asset_id} is not serviceable")
    return {
        "ready": not blockers,
        "blockers": blockers,
        "approved_budget_version": baseline.version if baseline and baseline.status == "approved" else None,
        "approved_budget": str(baseline.total_amount) if baseline and baseline.status == "approved" else "0.00",
        "milestone_count": len(milestones),
        "required_checklist_missing": int(missing_mob),
        "required_documents_missing": int(missing_docs),
        "critical_open_risks": int(critical),
        "planned_assets_unconfirmed": int(planned_assets),
    }


@router.post("/bootstrap")
def bootstrap_phase6_safe(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    result = base_bootstrap(db=db, principal=principal)
    branch_manager = db.scalar(select(Role).where(Role.company_id == principal.user.company_id, Role.code == "BRANCH_MANAGER"))
    approve = db.scalar(select(Permission).where(Permission.code == "projects.approve"))
    if branch_manager and approve and not db.scalar(select(RolePermission.id).where(RolePermission.role_id == branch_manager.id, RolePermission.permission_id == approve.id)):
        db.add(RolePermission(role_id=branch_manager.id, permission_id=approve.id))
        commit(db)
    return result


@router.get("/catalog")
def project_catalog_safe(db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    if not principal.has_permission_anywhere("projects.view"):
        raise HTTPException(status_code=403, detail="Permission required: projects.view")
    company_id = principal.user.company_id
    branches = [row for row in db.scalars(select(Branch).where(Branch.company_id == company_id, Branch.is_active.is_(True)).order_by(Branch.name)).all() if principal.can("projects.view", branch_id=row.id)]
    sites = [row for row in db.scalars(select(Site).where(Site.company_id == company_id, Site.is_active.is_(True)).order_by(Site.name)).all() if principal.can("projects.view", branch_id=row.branch_id, site_id=row.id)]
    employees = [row for row in db.scalars(select(Employee).where(Employee.company_id == company_id, Employee.employment_status.in_(["active", "probation", "notice"])).order_by(Employee.last_name, Employee.first_name)).all() if principal.can("projects.view", branch_id=row.branch_id, site_id=row.site_id)]
    assets = [row for row in db.scalars(select(FleetAsset).where(FleetAsset.company_id == company_id, FleetAsset.status != "disposed").order_by(FleetAsset.asset_number)).all() if principal.has_company_permission("projects.assets") or principal.can("projects.assets", branch_id=row.branch_id, site_id=row.site_id)]
    existing_tender_ids = set(db.scalars(select(Project.tender_id).where(Project.company_id == company_id, Project.tender_id.is_not(None))).all())
    awarded = [row for row in db.scalars(select(Tender).where(Tender.company_id == company_id, Tender.status == "awarded").order_by(Tender.id.desc())).all() if row.id not in existing_tender_ids and principal.can("projects.mobilise", branch_id=row.branch_id, site_id=row.site_id)]
    documents = [row for row in db.scalars(select(Document).where(Document.company_id == company_id, Document.status == "active").order_by(Document.id.desc()).limit(500)).all() if row.branch_id is None or principal.can("projects.view", branch_id=row.branch_id, site_id=row.site_id)]
    return {
        "branches": [row_dict(row) for row in branches],
        "sites": [row_dict(row) for row in sites],
        "employees": [{"id": row.id, "employee_number": row.employee_number, "branch_id": row.branch_id, "site_id": row.site_id, "name": f"{row.first_name} {row.last_name}", "job_title": row.job_title} for row in employees],
        "assets": [{"id": row.id, "asset_number": row.asset_number, "branch_id": row.branch_id, "site_id": row.site_id, "name": f"{row.make} {row.model}", "asset_type": row.asset_type, "status": row.status, "serviceability": row.serviceability} for row in assets],
        "awarded_tenders": [{"id": row.id, "tender_number": row.tender_number, "branch_id": row.branch_id, "title": row.title, "client_name": row.client_name, "tender_price": str(row.tender_price)} for row in awarded],
        "documents": [{"id": row.id, "branch_id": row.branch_id, "site_id": row.site_id, "title": row.title, "category": row.category} for row in documents],
        "permissions": sorted(code for code in principal.permission_codes if code.startswith("projects.")),
    }


@router.get("/{project_id:int}")
def project_detail_safe(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    result = base_project_detail(project_id=project_id, db=db, principal=principal)
    project = db.get(Project, project_id)
    if project:
        result["readiness"] = strict_readiness_state(db, project)
    return result


@router.get("/{project_id:int}/readiness")
def get_readiness_safe(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id)
    return strict_readiness_state(db, project)


@router.post("/{project_id:int}/readiness-approval")
def request_readiness_approval_safe(project_id: int, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    project = project_or_404(db, principal, project_id, "projects.mobilise")
    if project.status == "ready" or project.readiness_status == "ready":
        request = db.get(ApprovalRequest, project.mobilisation_approval_request_id) if project.mobilisation_approval_request_id else None
        return row_dict(request) if request else {"status": "ready"}
    state = strict_readiness_state(db, project)
    if not state["ready"]:
        raise HTTPException(status_code=409, detail={"message": "Project is not ready for mobilisation approval", "blockers": state["blockers"]})
    if project.mobilisation_approval_request_id:
        existing = db.get(ApprovalRequest, project.mobilisation_approval_request_id)
        if existing and existing.status == "pending":
            return row_dict(existing)
    request = create_approval(db, principal, project, "PROJECT_MOBILISATION", "project_mobilisation", str(project.id), f"Project mobilisation readiness: {project.project_number} - {project.name}", project.contract_amount)
    project.mobilisation_approval_request_id = request.id
    project.readiness_status = "pending"
    audit(db, principal, "project.readiness.submitted", "approval_request", request.id, project=project, detail={"reference": request.reference})
    commit(db)
    return row_dict(request)


@router.post("/approvals/{request_id:int}/decision")
def decide_project_approval_safe(request_id: int, payload: ApprovalDecisionInput, db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict[str, Any]:
    request = db.get(ApprovalRequest, request_id)
    if not request or request.company_id != principal.user.company_id or request.entity_type not in {"project_budget", "project_mobilisation"}:
        raise HTTPException(status_code=404, detail="Project approval request not found")
    if request.entity_type == "project_budget":
        baseline = db.get(ProjectBudgetBaseline, int(request.entity_id))
        if not baseline:
            raise HTTPException(status_code=404, detail="Project budget baseline not found")
        project = project_or_404(db, principal, baseline.project_id, "projects.approve")
    else:
        baseline = None
        project = project_or_404(db, principal, int(request.entity_id), "projects.approve")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval request is already {request.status}")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step:
        raise HTTPException(status_code=409, detail="Current approval step is not configured")
    if not assignment_authorised(db, principal, step.role_id, project):
        raise HTTPException(status_code=403, detail="Your active role assignment is not authorised for this approval step")
    if request.requested_by == principal.user.full_name and not bool(approval_setting(db, project.company_id).get("allow_self_approval", False)):
        raise HTTPException(status_code=422, detail="Self-approval is disabled by company approval policy")
    if payload.decision == "approve" and request.entity_type == "project_mobilisation":
        state = strict_readiness_state(db, project)
        if not state["ready"]:
            raise HTTPException(status_code=409, detail={"message": "Project is no longer ready for mobilisation approval", "blockers": state["blockers"]})
    db.add(ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=step.role_id, actor_name=principal.user.full_name, action=payload.decision, comment=payload.comment))
    if payload.decision == "reject":
        request.status = "rejected"; request.completed_at = utcnow()
    else:
        approved_count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved_count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status = "approved"; request.completed_at = utcnow()
    if baseline:
        if request.status == "rejected":
            baseline.status = "rejected"
        elif request.status == "approved":
            for previous in db.scalars(select(ProjectBudgetBaseline).where(ProjectBudgetBaseline.project_id == project.id, ProjectBudgetBaseline.status == "approved", ProjectBudgetBaseline.id != baseline.id)).all():
                previous.status = "superseded"
            baseline.status = "approved"; baseline.approved_at = utcnow(); project.baseline_budget = baseline.total_amount
    else:
        if request.status == "rejected":
            project.readiness_status = "rejected"
        elif request.status == "approved":
            project.readiness_status = "ready"; project.status = "ready"
            snapshot_data = snapshot_payload(db, project)
            snapshot_data["readiness"] = strict_readiness_state(db, project)
            db.add(ProjectReadinessSnapshot(company_id=project.company_id, project_id=project.id, version=(db.scalar(select(func.max(ProjectReadinessSnapshot.version)).where(ProjectReadinessSnapshot.project_id == project.id)) or 0) + 1, approval_request_id=request.id, snapshot=snapshot_data, created_by=principal.user.full_name))
    audit(db, principal, f"project.approval.{payload.decision}", "approval_request", request.id, project=project, detail={"entity_type": request.entity_type, "status": request.status, "step": step.step_order})
    commit(db)
    return row_dict(request)
