from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from database.config.config import settings
from database.multi_tenant_school_management.models import School, SchoolMembership, User
from database.multi_tenant_school_management.schemas.school import (
    SchoolCreate,
    SchoolMembershipResponse,
    SchoolResponse,
    SchoolUpdate,
    SchoolWorkspaceResponse,
)
from database.session import get_db
from routes.service.layer import school as school_service
from utils.auth.tokens import get_current_user
from utils.school_context import SCHOOL_WORKSPACE_COOKIE, SchoolContext, get_school_context

router = APIRouter(prefix="/schools", tags=["Schools"])


ROLE_CAPABILITIES: dict[str, list[str]] = {
    "school_admin": ["school.manage", "users.manage", "academics.manage", "finance.manage", "reports.view"],
    "principal": ["school.manage", "academics.manage", "staff.manage", "reports.view"],
    "vice_principal": ["academics.manage", "staff.manage", "reports.view"],
    "teacher": ["classes.view", "attendance.manage", "assessments.manage", "students.view"],
    "class_teacher": ["classes.view", "attendance.manage", "assessments.manage", "students.view"],
    "bursar": ["finance.manage", "reports.view"],
    "accountant": ["finance.manage", "reports.view"],
    "cashier": ["payments.manage"],
    "student": ["learning.view", "results.view", "fees.view"],
    "parent": ["children.view", "results.view", "fees.view"],
    "guardian": ["children.view", "results.view", "fees.view"],
}


def _role_value(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


@router.post("/", response_model=SchoolResponse, status_code=201)
def create_school(
    data: SchoolCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return school_service.create_school_service(db, data, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/mine", response_model=list[SchoolMembershipResponse])
def my_school_workspaces(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if _role_value(user) == "super_admin":
        return [
            SchoolMembershipResponse(
                id=None,
                school_id=school.id,
                role="super_admin",
                title="Platform Administrator",
                is_default=False,
                school=school,
            )
            for school in db.query(School).filter(School.is_active.is_(True)).order_by(School.name.asc()).all()
        ]

    memberships = (
        db.query(SchoolMembership)
        .filter(
            SchoolMembership.user_id == user.id,
            SchoolMembership.is_active.is_(True),
        )
        .order_by(SchoolMembership.is_default.desc(), SchoolMembership.created_at.asc())
        .all()
    )
    result = [
        SchoolMembershipResponse(
            id=membership.id,
            school_id=membership.school_id,
            role=membership.role,
            title=membership.title,
            is_default=membership.is_default,
            school=membership.school,
        )
        for membership in memberships
        if membership.school is not None and membership.school.is_active
    ]

    if user.school_id is not None and all(item.school_id != user.school_id for item in result):
        school = db.get(School, user.school_id)
        if school is not None and school.is_active:
            result.append(
                SchoolMembershipResponse(
                    id=None,
                    school_id=school.id,
                    role=_role_value(user),
                    title="Legacy school membership",
                    is_default=True,
                    school=school,
                )
            )
    return result


@router.get("/workspace", response_model=SchoolWorkspaceResponse)
def current_school_workspace(
    context: SchoolContext = Depends(get_school_context),
    db: Session = Depends(get_db),
):
    school = db.get(School, context.school_id)
    if school is None:
        raise HTTPException(status_code=404, detail="School not found")
    capabilities = ["*"] if context.is_platform_admin else ROLE_CAPABILITIES.get(context.role, [])
    return SchoolWorkspaceResponse(
        school=school,
        role=context.role,
        is_platform_admin=context.is_platform_admin,
        capabilities=capabilities,
    )


@router.post("/{school_id}/activate")
def activate_school_workspace(
    school_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        school = school_service.get_school_service(db, school_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if school is None or not school.is_active:
        raise HTTPException(status_code=404, detail="School not found")

    response.set_cookie(
        SCHOOL_WORKSPACE_COOKIE,
        str(school_id),
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        path="/",
    )
    return {"active_school_id": str(school_id), "school": SchoolResponse.model_validate(school)}


@router.get("/", response_model=list[SchoolResponse])
def get_schools(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return school_service.get_schools_service(db, user)


@router.get("/{school_id}", response_model=SchoolResponse)
def get_school(
    school_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        school = school_service.get_school_service(db, school_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not school:
        raise HTTPException(status_code=404, detail="School not found")
    return school


@router.put("/{school_id}", response_model=SchoolResponse)
def update_school(
    school_id: UUID,
    data: SchoolUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return school_service.update_school_service(db, school_id, data, user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete("/{school_id}")
def delete_school(
    school_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        school_service.delete_school_service(db, school_id, user)
        return {"message": "School deleted successfully"}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
