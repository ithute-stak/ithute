from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import School, SchoolMembership, User
from database.session import get_db
from utils.auth.tokens import get_current_user
from utils.convex import current_school_id


SCHOOL_WORKSPACE_COOKIE = "ithute_tutor_school"


@dataclass(frozen=True)
class SchoolContext:
    school_id: UUID
    role: str
    user_id: UUID
    membership_id: UUID | None = None
    is_platform_admin: bool = False


def _activate(context: SchoolContext) -> SchoolContext:
    current_school_id.set(str(context.school_id))
    return context


def _selected_school_id(request: Request) -> UUID | None:
    raw = request.headers.get("X-School-ID") or request.cookies.get(SCHOOL_WORKSPACE_COOKIE)
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid school workspace id") from exc


def _active_memberships(db: Session, user: User) -> list[SchoolMembership]:
    return (
        db.query(SchoolMembership)
        .filter(
            SchoolMembership.user_id == user.id,
            SchoolMembership.is_active.is_(True),
        )
        .order_by(SchoolMembership.is_default.desc(), SchoolMembership.created_at.asc())
        .all()
    )


async def get_school_context(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SchoolContext:
    selected = _selected_school_id(request)
    is_platform_admin = str(user.role) == "super_admin" or getattr(user.role, "value", None) == "super_admin"

    if selected is not None:
        school = db.get(School, selected)
        if school is None or not school.is_active:
            raise HTTPException(status_code=404, detail="school workspace not found")

        if is_platform_admin:
            return _activate(SchoolContext(
                school_id=selected,
                role="super_admin",
                user_id=user.id,
                is_platform_admin=True,
            ))

        membership = (
            db.query(SchoolMembership)
            .filter(
                SchoolMembership.user_id == user.id,
                SchoolMembership.school_id == selected,
                SchoolMembership.is_active.is_(True),
            )
            .first()
        )
        if membership is not None:
            return _activate(SchoolContext(
                school_id=selected,
                role=membership.role,
                user_id=user.id,
                membership_id=membership.id,
            ))

        if user.school_id == selected:
            role = getattr(user.role, "value", str(user.role))
            return _activate(SchoolContext(school_id=selected, role=role, user_id=user.id))

        raise HTTPException(status_code=403, detail="you do not belong to this school workspace")

    memberships = _active_memberships(db, user)
    if len(memberships) == 1:
        membership = memberships[0]
        return _activate(SchoolContext(
            school_id=membership.school_id,
            role=membership.role,
            user_id=user.id,
            membership_id=membership.id,
        ))

    if user.school_id is not None:
        role = getattr(user.role, "value", str(user.role))
        return _activate(SchoolContext(school_id=user.school_id, role=role, user_id=user.id))

    if is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="select a school workspace before using this endpoint",
        )

    if not memberships:
        raise HTTPException(status_code=403, detail="no active school membership")

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="multiple school memberships found; select a school workspace",
    )


def require_school_roles(*allowed_roles: str):
    allowed = set(allowed_roles)

    def dependency(context: SchoolContext = Depends(get_school_context)) -> SchoolContext:
        if context.is_platform_admin or context.role in allowed:
            return context
        raise HTTPException(status_code=403, detail="insufficient permission in this school workspace")

    return dependency
