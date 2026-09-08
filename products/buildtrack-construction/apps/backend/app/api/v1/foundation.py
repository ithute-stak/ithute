from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    ApprovalAction,
    ApprovalRequest,
    ApprovalStep,
    ApprovalWorkflow,
    AuditLog,
    Branch,
    Company,
    CompanySetting,
    CostCentre,
    Department,
    Document,
    DocumentVersion,
    MasterDataCategory,
    MasterDataItem,
    NumberSequence,
    Permission,
    Role,
    RolePermission,
    Site,
)

router = APIRouter(prefix="/foundation", tags=["Phase 1 - Core Platform"])
settings = get_settings()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def row_dict(row: Any) -> dict[str, Any]:
    return {column.name: json_value(getattr(row, column.name)) for column in row.__table__.columns}


def current_company(db: Session) -> Company:
    company = db.scalar(select(Company).order_by(Company.id).limit(1))
    if not company:
        raise HTTPException(status_code=409, detail="BuildTrack has not been bootstrapped. Complete Phase 1 company setup first.")
    return company


def checked(db: Session, model: Any, row_id: int, label: str) -> Any:
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return row


def audit(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | int | None,
    actor: str = "system",
    company_id: int | None = None,
    branch_id: int | None = None,
    site_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            company_id=company_id,
            branch_id=branch_id,
            site_id=site_id,
            actor=actor.strip() or "system",
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            detail=detail or {},
        )
    )


def commit(db: Session, duplicate_detail: str = "A record with the same code already exists") -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=duplicate_detail) from error


def ensure_company_scope(company: Company, row: Any, label: str) -> None:
    if getattr(row, "company_id", company.id) != company.id:
        raise HTTPException(status_code=422, detail=f"{label} does not belong to the active company")


def ensure_branch(db: Session, company: Company, branch_id: int | None) -> Branch | None:
    if branch_id is None:
        return None
    branch = checked(db, Branch, branch_id, "Branch")
    ensure_company_scope(company, branch, "Branch")
    return branch


def ensure_site(db: Session, company: Company, site_id: int | None, branch_id: int | None = None) -> Site | None:
    if site_id is None:
        return None
    site = checked(db, Site, site_id, "Site")
    ensure_company_scope(company, site, "Site")
    if branch_id is not None and site.branch_id != branch_id:
        raise HTTPException(status_code=422, detail="Site does not belong to the selected branch")
    return site


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(default="Nthane Brothers", min_length=2, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    code: str = Field(default="NTHANE", min_length=2, max_length=32)
    registration_number: str | None = Field(default=None, max_length=100)
    tax_number: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    physical_address: str | None = None
    head_office_name: str = Field(default="Head Office", min_length=2, max_length=255)
    head_office_code: str = Field(default="HO", min_length=1, max_length=32)
    head_office_district: str = Field(default="Maseru", max_length=120)
    actor: str = Field(default="System Setup", max_length=255)


class CompanyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    registration_number: str | None = Field(default=None, max_length=100)
    tax_number: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    physical_address: str | None = None
    postal_address: str | None = None
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)
    actor: str = Field(default="Phase 1 Admin", max_length=255)


class BranchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=2, max_length=255)
    branch_type: Literal["head_office", "branch", "regional_office", "yard", "workshop"] = "branch"
    district: str | None = Field(default=None, max_length=120)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    manager_name: str | None = Field(default=None, max_length=255)
    manager_email: str | None = Field(default=None, max_length=255)
    manager_phone: str | None = Field(default=None, max_length=64)
    is_active: bool = True
    actor: str = "Phase 1 Admin"


class SiteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=2, max_length=255)
    site_type: str = Field(default="project_site", max_length=48)
    district: str | None = Field(default=None, max_length=120)
    location: str | None = None
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    responsible_officer: str | None = Field(default=None, max_length=255)
    responsible_phone: str | None = Field(default=None, max_length=64)
    is_active: bool = True
    actor: str = "Phase 1 Admin"


class DepartmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int | None = None
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    manager_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    actor: str = "Phase 1 Admin"


class CostCentreInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int | None = None
    site_id: int | None = None
    department_id: int | None = None
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=2, max_length=255)
    cost_centre_type: str = Field(default="operational", max_length=48)
    description: str | None = None
    is_active: bool = True
    actor: str = "Phase 1 Admin"


class RoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    scope_level: Literal["company", "branch", "site"] = "company"
    permission_ids: list[int] = Field(default_factory=list)
    is_active: bool = True
    actor: str = "Phase 1 Admin"


class WorkflowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int | None = None
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    module: str = Field(min_length=2, max_length=64)
    description: str | None = None
    min_amount: Decimal | None = Field(default=None, ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True
    actor: str = "Phase 1 Admin"


class ApprovalStepInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_order: int = Field(ge=1, le=50)
    name: str = Field(min_length=2, max_length=160)
    role_id: int
    required_approvals: int = Field(default=1, ge=1, le=20)
    escalation_hours: int | None = Field(default=None, ge=1, le=8760)
    actor: str = "Phase 1 Admin"


class ApprovalRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_id: int
    branch_id: int | None = None
    site_id: int | None = None
    entity_type: str = Field(min_length=2, max_length=80)
    entity_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=2, max_length=255)
    amount: Decimal | None = Field(default=None, ge=0)
    requested_by: str = Field(min_length=2, max_length=255)


class ApprovalActionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: int
    actor_name: str = Field(min_length=2, max_length=255)
    action: Literal["approve", "reject"]
    comment: str | None = None


class SettingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=2, max_length=100)
    value: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    actor: str = "Phase 1 Admin"


class SequenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=2, max_length=160)
    prefix: str = Field(min_length=1, max_length=24)
    next_number: int = Field(default=1, ge=1)
    padding: int = Field(default=5, ge=2, le=12)
    reset_period: Literal["never", "yearly", "monthly"] = "never"
    is_active: bool = True
    actor: str = "Phase 1 Admin"


class MasterCategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=160)
    description: str | None = None
    actor: str = "Phase 1 Admin"


class MasterItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    value: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    actor: str = "Phase 1 Admin"


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    branch_id: int | None = None
    site_id: int | None = None
    title: str = Field(min_length=2, max_length=255)
    category: str = Field(min_length=2, max_length=100)
    entity_type: str | None = Field(default=None, max_length=80)
    entity_id: str | None = Field(default=None, max_length=100)
    confidentiality: Literal["public", "internal", "confidential", "restricted"] = "internal"
    created_by: str = Field(default="Phase 1 Admin", max_length=255)


PERMISSION_BLUEPRINT: dict[str, tuple[str, ...]] = {
    "company": ("view", "manage"),
    "branches": ("view", "manage"),
    "sites": ("view", "manage"),
    "departments": ("view", "manage"),
    "cost_centres": ("view", "manage"),
    "roles": ("view", "manage"),
    "approvals": ("view", "request", "approve", "manage"),
    "documents": ("view", "upload", "manage"),
    "master_data": ("view", "manage"),
    "audit": ("view",),
    "tenders": ("view", "manage", "approve"),
    "projects": ("view", "manage", "approve"),
    "people": ("view", "manage", "approve"),
    "fleet": ("view", "manage", "approve"),
    "procurement": ("view", "manage", "approve"),
    "subcontracts": ("view", "manage", "approve"),
    "commercial": ("view", "manage", "approve"),
    "reports": ("view", "export"),
}


@router.post("/bootstrap", status_code=201)
def bootstrap(payload: BootstrapRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.scalar(select(func.count()).select_from(Company)):
        raise HTTPException(status_code=409, detail="BuildTrack is already bootstrapped for its single company")

    company = Company(
        code=payload.code.strip().upper(),
        name=payload.name.strip(),
        legal_name=payload.legal_name,
        registration_number=payload.registration_number,
        tax_number=payload.tax_number,
        country="Lesotho",
        currency="LSL",
        currency_symbol="M",
        timezone="Africa/Maseru",
        phone=payload.phone,
        email=payload.email,
        physical_address=payload.physical_address,
    )
    db.add(company)
    db.flush()

    head_office = Branch(
        company_id=company.id,
        code=payload.head_office_code.strip().upper(),
        name=payload.head_office_name.strip(),
        branch_type="head_office",
        district=payload.head_office_district,
    )
    db.add(head_office)
    db.flush()

    departments: list[Department] = []
    for code, name in (
        ("EXEC", "Executive Management"),
        ("FIN", "Finance"),
        ("HR", "Human Resources"),
        ("TND", "Tendering & Estimating"),
        ("PRJ", "Projects & Operations"),
        ("FLT", "Fleet & Plant"),
        ("PRC", "Procurement & Stores"),
        ("COM", "Commercial & Contracts"),
        ("HSE", "Health, Safety & Quality"),
    ):
        department = Department(company_id=company.id, branch_id=None, code=code, name=name)
        db.add(department)
        departments.append(department)
    db.flush()

    db.add(
        CostCentre(
            company_id=company.id,
            branch_id=head_office.id,
            code="HO-ADMIN",
            name="Head Office Administration",
            cost_centre_type="overhead",
        )
    )

    permissions: list[Permission] = []
    for module, actions in PERMISSION_BLUEPRINT.items():
        for permission_action in actions:
            permission = Permission(
                code=f"{module}.{permission_action}",
                module=module,
                action=permission_action,
                description=f"{permission_action.replace('_', ' ').title()} {module.replace('_', ' ')}",
            )
            db.add(permission)
            permissions.append(permission)
    db.flush()

    roles: dict[str, Role] = {}
    for code, name, scope, description in (
        ("SYSTEM_ADMIN", "System Administrator", "company", "Full BuildTrack administration"),
        ("HQ_EXECUTIVE", "Head Office Executive", "company", "Organisation-wide oversight and approvals"),
        ("BRANCH_MANAGER", "Branch Manager", "branch", "Operational management within an assigned branch"),
        ("SITE_MANAGER", "Site Manager", "site", "Operational management within an assigned site"),
        ("APPROVER", "Approver", "company", "Generic controlled approval authority"),
        ("AUDITOR", "Auditor / Read Only", "company", "Read-only governance and audit access"),
    ):
        role = Role(company_id=company.id, code=code, name=name, scope_level=scope, description=description, is_system=True)
        db.add(role)
        roles[code] = role
    db.flush()

    for permission in permissions:
        db.add(RolePermission(role_id=roles["SYSTEM_ADMIN"].id, permission_id=permission.id))
        if permission.action in {"view", "export", "approve"}:
            db.add(RolePermission(role_id=roles["HQ_EXECUTIVE"].id, permission_id=permission.id))
        if permission.action in {"view", "manage", "request"} and permission.module not in {"roles", "audit"}:
            db.add(RolePermission(role_id=roles["BRANCH_MANAGER"].id, permission_id=permission.id))
        if permission.action == "view":
            db.add(RolePermission(role_id=roles["AUDITOR"].id, permission_id=permission.id))
    approve_permission_ids = [permission.id for permission in permissions if permission.action == "approve"]
    for permission_id in approve_permission_ids:
        db.add(RolePermission(role_id=roles["APPROVER"].id, permission_id=permission_id))

    for code, name, prefix in (
        ("TENDER", "Tender Number", "TND"),
        ("PROJECT", "Project Number", "PRJ"),
        ("EMPLOYEE", "Employee Number", "EMP"),
        ("FLEET", "Fleet Asset Number", "FLT"),
        ("PURCHASE_ORDER", "Purchase Order", "PO"),
        ("SUBCONTRACT", "Subcontract Number", "SUB"),
        ("DOCUMENT", "Document Number", "DOC"),
        ("APPROVAL", "Approval Request", "APR"),
    ):
        db.add(NumberSequence(company_id=company.id, code=code, name=name, prefix=prefix, padding=5, reset_period="yearly"))

    for key, value, description in (
        ("localisation", {"country": "Lesotho", "currency": "LSL", "symbol": "M", "timezone": "Africa/Maseru"}, "Core localisation"),
        ("branch_control", {"require_branch": True, "require_site_when_applicable": True}, "Ownership rules for operational records"),
        ("approval_control", {"enabled": True, "allow_self_approval": False}, "Approval governance defaults"),
        ("document_control", {"versioning": True, "hash_files": True, "default_confidentiality": "internal"}, "Document governance defaults"),
    ):
        db.add(CompanySetting(company_id=company.id, key=key, value=value, description=description))

    district_category = MasterDataCategory(company_id=company.id, code="LESOTHO_DISTRICTS", name="Lesotho Districts")
    document_category = MasterDataCategory(company_id=company.id, code="DOCUMENT_CATEGORIES", name="Document Categories")
    db.add_all([district_category, document_category])
    db.flush()
    for index, district in enumerate(("Berea", "Butha-Buthe", "Leribe", "Mafeteng", "Maseru", "Mohale's Hoek", "Mokhotlong", "Qacha's Nek", "Quthing", "Thaba-Tseka"), start=1):
        db.add(MasterDataItem(category_id=district_category.id, code=district.upper().replace("'", "").replace("-", "_").replace(" ", "_"), name=district, sort_order=index))
    for index, category in enumerate(("Corporate", "Tender", "Project", "Employee", "Fleet", "Procurement", "Subcontract", "HSE", "Finance", "Legal"), start=1):
        db.add(MasterDataItem(category_id=document_category.id, code=category.upper(), name=category, sort_order=index))

    procurement_workflow = ApprovalWorkflow(
        company_id=company.id,
        code="PROCUREMENT_STANDARD",
        name="Standard Procurement Approval",
        module="procurement",
        description="Default controlled purchasing workflow. Thresholds can be adjusted from Phase 1 administration.",
        min_amount=Decimal("0"),
    )
    db.add(procurement_workflow)
    db.flush()
    db.add_all(
        [
            ApprovalStep(workflow_id=procurement_workflow.id, step_order=1, name="Branch / Operational Review", role_id=roles["BRANCH_MANAGER"].id, required_approvals=1, escalation_hours=24),
            ApprovalStep(workflow_id=procurement_workflow.id, step_order=2, name="Head Office Approval", role_id=roles["HQ_EXECUTIVE"].id, required_approvals=1, escalation_hours=48),
        ]
    )

    audit(
        db,
        action="phase1.bootstrap",
        entity_type="company",
        entity_id=company.id,
        actor=payload.actor,
        company_id=company.id,
        branch_id=head_office.id,
        detail={"company": company.name, "head_office": head_office.name},
    )
    commit(db, "Company setup conflicts with existing Phase 1 records")
    return {"company": row_dict(company), "head_office": row_dict(head_office), "message": "Phase 1 foundation bootstrapped"}


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    counts = {}
    for key, model in (
        ("branches", Branch),
        ("sites", Site),
        ("departments", Department),
        ("cost_centres", CostCentre),
        ("roles", Role),
        ("permissions", Permission),
        ("approval_workflows", ApprovalWorkflow),
        ("pending_approvals", ApprovalRequest),
        ("documents", Document),
        ("number_sequences", NumberSequence),
        ("master_data_categories", MasterDataCategory),
    ):
        statement = select(func.count()).select_from(model)
        if hasattr(model, "company_id"):
            statement = statement.where(model.company_id == company.id)
        if key == "pending_approvals":
            statement = statement.where(ApprovalRequest.status == "pending")
        counts[key] = db.scalar(statement) or 0
    return {"company": row_dict(company), "counts": counts, "phase": 1, "phase_status": "operational"}


@router.get("/company")
def get_company(db: Session = Depends(get_db)) -> dict[str, Any]:
    return row_dict(current_company(db))


@router.patch("/company")
def update_company(payload: CompanyUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    changes = payload.model_dump(exclude_unset=True)
    actor = changes.pop("actor", "Phase 1 Admin")
    for key, value in changes.items():
        setattr(company, key, value)
    audit(db, action="company.update", entity_type="company", entity_id=company.id, actor=actor, company_id=company.id, detail=changes)
    commit(db)
    db.refresh(company)
    return row_dict(company)


def list_company_rows(db: Session, model: Any) -> list[dict[str, Any]]:
    company = current_company(db)
    rows = db.scalars(select(model).where(model.company_id == company.id).order_by(model.id)).all()
    return [row_dict(row) for row in rows]


@router.get("/branches")
def list_branches(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_company_rows(db, Branch)


@router.post("/branches", status_code=201)
def create_branch(payload: BranchInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    row = Branch(company_id=company.id, **values)
    db.add(row)
    db.flush()
    audit(db, action="branch.create", entity_type="branch", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.put("/branches/{branch_id}")
def update_branch(branch_id: int, payload: BranchInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    row = checked(db, Branch, branch_id, "Branch")
    ensure_company_scope(company, row, "Branch")
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    for key, value in values.items():
        setattr(row, key, value)
    audit(db, action="branch.update", entity_type="branch", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.get("/sites")
def list_sites(branch_id: int | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    company = current_company(db)
    statement = select(Site).where(Site.company_id == company.id)
    if branch_id is not None:
        ensure_branch(db, company, branch_id)
        statement = statement.where(Site.branch_id == branch_id)
    return [row_dict(row) for row in db.scalars(statement.order_by(Site.id)).all()]


@router.post("/sites", status_code=201)
def create_site(payload: SiteInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    ensure_branch(db, company, payload.branch_id)
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    row = Site(company_id=company.id, **values)
    db.add(row)
    db.flush()
    audit(db, action="site.create", entity_type="site", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.branch_id, site_id=row.id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.put("/sites/{site_id}")
def update_site(site_id: int, payload: SiteInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    row = checked(db, Site, site_id, "Site")
    ensure_company_scope(company, row, "Site")
    ensure_branch(db, company, payload.branch_id)
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    for key, value in values.items():
        setattr(row, key, value)
    audit(db, action="site.update", entity_type="site", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.branch_id, site_id=row.id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.get("/departments")
def list_departments(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_company_rows(db, Department)


@router.post("/departments", status_code=201)
def create_department(payload: DepartmentInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    ensure_branch(db, company, payload.branch_id)
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    row = Department(company_id=company.id, **values)
    db.add(row)
    db.flush()
    audit(db, action="department.create", entity_type="department", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.branch_id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.put("/departments/{department_id}")
def update_department(department_id: int, payload: DepartmentInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    row = checked(db, Department, department_id, "Department")
    ensure_company_scope(company, row, "Department")
    ensure_branch(db, company, payload.branch_id)
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    for key, value in values.items():
        setattr(row, key, value)
    audit(db, action="department.update", entity_type="department", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.branch_id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.get("/cost-centres")
def list_cost_centres(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_company_rows(db, CostCentre)


@router.post("/cost-centres", status_code=201)
def create_cost_centre(payload: CostCentreInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    ensure_branch(db, company, payload.branch_id)
    ensure_site(db, company, payload.site_id, payload.branch_id)
    if payload.department_id is not None:
        department = checked(db, Department, payload.department_id, "Department")
        ensure_company_scope(company, department, "Department")
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    row = CostCentre(company_id=company.id, **values)
    db.add(row)
    db.flush()
    audit(db, action="cost_centre.create", entity_type="cost_centre", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.branch_id, site_id=row.site_id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.put("/cost-centres/{cost_centre_id}")
def update_cost_centre(cost_centre_id: int, payload: CostCentreInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    row = checked(db, CostCentre, cost_centre_id, "Cost centre")
    ensure_company_scope(company, row, "Cost centre")
    ensure_branch(db, company, payload.branch_id)
    ensure_site(db, company, payload.site_id, payload.branch_id)
    values = payload.model_dump(exclude={"actor"})
    values["code"] = values["code"].strip().upper()
    for key, value in values.items():
        setattr(row, key, value)
    audit(db, action="cost_centre.update", entity_type="cost_centre", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.branch_id, site_id=row.site_id, detail={"code": row.code, "name": row.name})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.get("/permissions")
def list_permissions(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [row_dict(row) for row in db.scalars(select(Permission).order_by(Permission.module, Permission.action)).all()]


@router.get("/roles")
def list_roles(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    company = current_company(db)
    roles = db.scalars(select(Role).where(Role.company_id == company.id).order_by(Role.id)).all()
    result = []
    for role in roles:
        permission_ids = list(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        result.append({**row_dict(role), "permission_ids": permission_ids})
    return result


@router.post("/roles", status_code=201)
def create_role(payload: RoleInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    permissions = db.scalars(select(Permission).where(Permission.id.in_(payload.permission_ids))).all() if payload.permission_ids else []
    if len(permissions) != len(set(payload.permission_ids)):
        raise HTTPException(status_code=422, detail="One or more permission IDs are invalid")
    row = Role(company_id=company.id, code=payload.code.strip().upper(), name=payload.name, description=payload.description, scope_level=payload.scope_level, is_active=payload.is_active)
    db.add(row)
    db.flush()
    for permission in permissions:
        db.add(RolePermission(role_id=row.id, permission_id=permission.id))
    audit(db, action="role.create", entity_type="role", entity_id=row.id, actor=payload.actor, company_id=company.id, detail={"code": row.code, "permission_ids": payload.permission_ids})
    commit(db)
    return {**row_dict(row), "permission_ids": payload.permission_ids}


@router.put("/roles/{role_id}")
def update_role(role_id: int, payload: RoleInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    row = checked(db, Role, role_id, "Role")
    ensure_company_scope(company, row, "Role")
    if row.is_system and payload.code.strip().upper() != row.code:
        raise HTTPException(status_code=422, detail="System role codes cannot be changed")
    permissions = db.scalars(select(Permission).where(Permission.id.in_(payload.permission_ids))).all() if payload.permission_ids else []
    if len(permissions) != len(set(payload.permission_ids)):
        raise HTTPException(status_code=422, detail="One or more permission IDs are invalid")
    row.name = payload.name
    row.description = payload.description
    row.scope_level = payload.scope_level
    row.is_active = payload.is_active
    db.execute(delete(RolePermission).where(RolePermission.role_id == row.id))
    for permission in permissions:
        db.add(RolePermission(role_id=row.id, permission_id=permission.id))
    audit(db, action="role.update", entity_type="role", entity_id=row.id, actor=payload.actor, company_id=company.id, detail={"permission_ids": payload.permission_ids})
    commit(db)
    return {**row_dict(row), "permission_ids": payload.permission_ids}


@router.get("/approval-workflows")
def list_workflows(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    company = current_company(db)
    workflows = db.scalars(select(ApprovalWorkflow).where(ApprovalWorkflow.company_id == company.id).order_by(ApprovalWorkflow.id)).all()
    output = []
    for workflow in workflows:
        steps = db.scalars(select(ApprovalStep).where(ApprovalStep.workflow_id == workflow.id).order_by(ApprovalStep.step_order)).all()
        output.append({**row_dict(workflow), "steps": [row_dict(step) for step in steps]})
    return output


@router.post("/approval-workflows", status_code=201)
def create_workflow(payload: WorkflowInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    ensure_branch(db, company, payload.branch_id)
    if payload.min_amount is not None and payload.max_amount is not None and payload.max_amount < payload.min_amount:
        raise HTTPException(status_code=422, detail="max_amount must be greater than or equal to min_amount")
    row = ApprovalWorkflow(company_id=company.id, **payload.model_dump(exclude={"actor"}))
    row.code = row.code.strip().upper()
    db.add(row)
    db.flush()
    audit(db, action="approval_workflow.create", entity_type="approval_workflow", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=row.branch_id, detail={"code": row.code, "module": row.module})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.post("/approval-workflows/{workflow_id}/steps", status_code=201)
def create_workflow_step(workflow_id: int, payload: ApprovalStepInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    workflow = checked(db, ApprovalWorkflow, workflow_id, "Approval workflow")
    ensure_company_scope(company, workflow, "Approval workflow")
    role = checked(db, Role, payload.role_id, "Role")
    ensure_company_scope(company, role, "Role")
    row = ApprovalStep(workflow_id=workflow.id, **payload.model_dump(exclude={"actor"}))
    db.add(row)
    db.flush()
    audit(db, action="approval_step.create", entity_type="approval_step", entity_id=row.id, actor=payload.actor, company_id=company.id, branch_id=workflow.branch_id, detail={"workflow_id": workflow.id, "step_order": row.step_order, "role_id": row.role_id})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.get("/approval-requests")
def list_approval_requests(status: str | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    company = current_company(db)
    statement = select(ApprovalRequest).where(ApprovalRequest.company_id == company.id)
    if status:
        statement = statement.where(ApprovalRequest.status == status)
    return [row_dict(row) for row in db.scalars(statement.order_by(ApprovalRequest.id.desc())).all()]


def next_reference(db: Session, company: Company, sequence_code: str) -> str:
    sequence = db.scalar(select(NumberSequence).where(NumberSequence.company_id == company.id, NumberSequence.code == sequence_code).with_for_update())
    if not sequence:
        raise HTTPException(status_code=409, detail=f"Number sequence {sequence_code} is not configured")
    now = utcnow()
    reset_key = None
    if sequence.reset_period == "yearly":
        reset_key = now.strftime("%Y")
    elif sequence.reset_period == "monthly":
        reset_key = now.strftime("%Y%m")
    if reset_key and sequence.last_reset_key != reset_key:
        sequence.next_number = 1
        sequence.last_reset_key = reset_key
    number = sequence.next_number
    sequence.next_number += 1
    period = f"-{reset_key}" if reset_key else ""
    return f"{sequence.prefix}{period}-{number:0{sequence.padding}d}"


@router.post("/approval-requests", status_code=201)
def create_approval_request(payload: ApprovalRequestInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    workflow = checked(db, ApprovalWorkflow, payload.workflow_id, "Approval workflow")
    ensure_company_scope(company, workflow, "Approval workflow")
    ensure_branch(db, company, payload.branch_id)
    ensure_site(db, company, payload.site_id, payload.branch_id)
    if not db.scalar(select(func.count()).select_from(ApprovalStep).where(ApprovalStep.workflow_id == workflow.id)):
        raise HTTPException(status_code=409, detail="Approval workflow has no approval steps")
    if payload.amount is not None:
        if workflow.min_amount is not None and payload.amount < workflow.min_amount:
            raise HTTPException(status_code=422, detail="Amount is below this workflow's minimum threshold")
        if workflow.max_amount is not None and payload.amount > workflow.max_amount:
            raise HTTPException(status_code=422, detail="Amount exceeds this workflow's maximum threshold")
    row = ApprovalRequest(
        company_id=company.id,
        reference=next_reference(db, company, "APPROVAL"),
        **payload.model_dump(),
    )
    db.add(row)
    db.flush()
    audit(db, action="approval_request.create", entity_type="approval_request", entity_id=row.id, actor=payload.requested_by, company_id=company.id, branch_id=row.branch_id, site_id=row.site_id, detail={"reference": row.reference, "workflow_id": row.workflow_id})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.post("/approval-requests/{request_id}/actions")
def act_on_approval(request_id: int, payload: ApprovalActionInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    request = checked(db, ApprovalRequest, request_id, "Approval request")
    ensure_company_scope(company, request, "Approval request")
    if request.status != "pending":
        raise HTTPException(status_code=409, detail=f"Approval request is already {request.status}")
    step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order == request.current_step_order))
    if not step:
        raise HTTPException(status_code=409, detail="Current approval step is not configured")
    if step.role_id != payload.role_id:
        raise HTTPException(status_code=403, detail="Selected role is not authorised for the current approval step")
    action = ApprovalAction(request_id=request.id, step_order=step.step_order, role_id=payload.role_id, actor_name=payload.actor_name, action=payload.action, comment=payload.comment)
    db.add(action)
    if payload.action == "reject":
        request.status = "rejected"
        request.completed_at = utcnow()
    else:
        approved_count = (db.scalar(select(func.count()).select_from(ApprovalAction).where(ApprovalAction.request_id == request.id, ApprovalAction.step_order == step.step_order, ApprovalAction.action == "approve")) or 0) + 1
        if approved_count >= step.required_approvals:
            next_step = db.scalar(select(ApprovalStep).where(ApprovalStep.workflow_id == request.workflow_id, ApprovalStep.step_order > step.step_order).order_by(ApprovalStep.step_order).limit(1))
            if next_step:
                request.current_step_order = next_step.step_order
            else:
                request.status = "approved"
                request.completed_at = utcnow()
    audit(db, action=f"approval_request.{payload.action}", entity_type="approval_request", entity_id=request.id, actor=payload.actor_name, company_id=company.id, branch_id=request.branch_id, site_id=request.site_id, detail={"reference": request.reference, "step_order": step.step_order, "role_id": payload.role_id})
    commit(db)
    db.refresh(request)
    return row_dict(request)


@router.get("/settings")
def list_settings(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_company_rows(db, CompanySetting)


@router.put("/settings/{key}")
def upsert_setting(key: str, payload: SettingInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    canonical_key = key.strip().lower()
    if canonical_key != payload.key.strip().lower():
        raise HTTPException(status_code=422, detail="Path setting key must match payload key")
    row = db.scalar(select(CompanySetting).where(CompanySetting.company_id == company.id, CompanySetting.key == canonical_key))
    if row is None:
        row = CompanySetting(company_id=company.id, key=canonical_key, value=payload.value, description=payload.description)
        db.add(row)
        db.flush()
    else:
        row.value = payload.value
        row.description = payload.description
    audit(db, action="setting.upsert", entity_type="company_setting", entity_id=row.id, actor=payload.actor, company_id=company.id, detail={"key": canonical_key})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.get("/number-sequences")
def list_sequences(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return list_company_rows(db, NumberSequence)


@router.post("/number-sequences", status_code=201)
def create_sequence(payload: SequenceInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    row = NumberSequence(company_id=company.id, **payload.model_dump(exclude={"actor"}))
    row.code = row.code.strip().upper()
    row.prefix = row.prefix.strip().upper()
    db.add(row)
    db.flush()
    audit(db, action="number_sequence.create", entity_type="number_sequence", entity_id=row.id, actor=payload.actor, company_id=company.id, detail={"code": row.code, "prefix": row.prefix})
    commit(db)
    return row_dict(row)


@router.post("/number-sequences/{sequence_id}/next")
def issue_number(sequence_id: int, actor: str = Query(default="Phase 1 Admin", max_length=255), db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    sequence = checked(db, NumberSequence, sequence_id, "Number sequence")
    ensure_company_scope(company, sequence, "Number sequence")
    reference = next_reference(db, company, sequence.code)
    audit(db, action="number_sequence.issue", entity_type="number_sequence", entity_id=sequence.id, actor=actor, company_id=company.id, detail={"reference": reference})
    commit(db)
    return {"reference": reference, "sequence": sequence.code}


@router.get("/master-data/categories")
def list_master_categories(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    company = current_company(db)
    categories = db.scalars(select(MasterDataCategory).where(MasterDataCategory.company_id == company.id).order_by(MasterDataCategory.name)).all()
    result = []
    for category in categories:
        items = db.scalars(select(MasterDataItem).where(MasterDataItem.category_id == category.id).order_by(MasterDataItem.sort_order, MasterDataItem.name)).all()
        result.append({**row_dict(category), "items": [row_dict(item) for item in items]})
    return result


@router.post("/master-data/categories", status_code=201)
def create_master_category(payload: MasterCategoryInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    row = MasterDataCategory(company_id=company.id, code=payload.code.strip().upper(), name=payload.name, description=payload.description)
    db.add(row)
    db.flush()
    audit(db, action="master_data.category.create", entity_type="master_data_category", entity_id=row.id, actor=payload.actor, company_id=company.id, detail={"code": row.code})
    commit(db)
    return row_dict(row)


@router.post("/master-data/categories/{category_id}/items", status_code=201)
def create_master_item(category_id: int, payload: MasterItemInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    category = checked(db, MasterDataCategory, category_id, "Master-data category")
    ensure_company_scope(company, category, "Master-data category")
    row = MasterDataItem(category_id=category.id, code=payload.code.strip().upper(), name=payload.name, value=payload.value, sort_order=payload.sort_order)
    db.add(row)
    db.flush()
    audit(db, action="master_data.item.create", entity_type="master_data_item", entity_id=row.id, actor=payload.actor, company_id=company.id, detail={"category": category.code, "code": row.code})
    commit(db)
    return row_dict(row)


@router.get("/documents")
def list_documents(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    company = current_company(db)
    documents = db.scalars(select(Document).where(Document.company_id == company.id).order_by(Document.id.desc())).all()
    output = []
    for document in documents:
        versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id).order_by(DocumentVersion.version_number.desc())).all()
        output.append({**row_dict(document), "versions": [row_dict(version) for version in versions]})
    return output


@router.post("/documents", status_code=201)
def create_document(payload: DocumentInput, db: Session = Depends(get_db)) -> dict[str, Any]:
    company = current_company(db)
    ensure_branch(db, company, payload.branch_id)
    ensure_site(db, company, payload.site_id, payload.branch_id)
    document_number = next_reference(db, company, "DOCUMENT")
    row = Document(company_id=company.id, document_number=document_number, **payload.model_dump())
    db.add(row)
    db.flush()
    audit(db, action="document.create", entity_type="document", entity_id=row.id, actor=payload.created_by, company_id=company.id, branch_id=row.branch_id, site_id=row.site_id, detail={"document_number": document_number, "title": row.title})
    commit(db)
    db.refresh(row)
    return row_dict(row)


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    return cleaned[:180] or "document.bin"


@router.post("/documents/{document_id}/versions", status_code=201)
async def upload_document_version(
    document_id: int,
    file: UploadFile = File(...),
    uploaded_by: str = Form(default="Phase 1 Admin"),
    note: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    company = current_company(db)
    document = checked(db, Document, document_id, "Document")
    ensure_company_scope(company, document, "Document")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded document is empty")
    max_bytes = 25 * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="Document exceeds the 25 MB Phase 1 upload limit")
    latest = db.scalar(select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document.id)) or 0
    version_number = int(latest) + 1
    filename = safe_filename(file.filename or "document.bin")
    media_root = Path(getattr(settings, "media_root", "media")).resolve()
    target_dir = media_root / f"company-{company.id}" / "documents" / str(document.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"v{version_number:03d}-{filename}"
    target.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    row = DocumentVersion(
        document_id=document.id,
        version_number=version_number,
        original_filename=filename,
        stored_path=str(target.relative_to(media_root)),
        content_type=file.content_type,
        file_size=len(content),
        sha256=digest,
        note=note,
        uploaded_by=uploaded_by,
    )
    db.add(row)
    audit(db, action="document.version.upload", entity_type="document", entity_id=document.id, actor=uploaded_by, company_id=company.id, branch_id=document.branch_id, site_id=document.site_id, detail={"version": version_number, "filename": filename, "sha256": digest})
    commit(db)
    db.refresh(row)
    return row_dict(row)


@router.get("/audit")
def list_audit(
    branch_id: int | None = None,
    site_id: int | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    company = current_company(db)
    statement = select(AuditLog).where(AuditLog.company_id == company.id)
    if branch_id is not None:
        ensure_branch(db, company, branch_id)
        statement = statement.where(AuditLog.branch_id == branch_id)
    if site_id is not None:
        ensure_site(db, company, site_id)
        statement = statement.where(AuditLog.site_id == site_id)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    rows = db.scalars(statement.order_by(AuditLog.occurred_at.desc()).limit(limit)).all()
    return [row_dict(row) for row in rows]
