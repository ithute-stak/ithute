import re
from uuid import UUID

from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import School, SchoolMembership, User
from database.multi_tenant_school_management.schemas.school import SchoolCreate, SchoolUpdate
from routes.service.crud import school as school_crud


def _role_value(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:120] or "school"


def _membership(db: Session, user: User, school_id: UUID) -> SchoolMembership | None:
    return (
        db.query(SchoolMembership)
        .filter(
            SchoolMembership.user_id == user.id,
            SchoolMembership.school_id == school_id,
            SchoolMembership.is_active.is_(True),
        )
        .first()
    )


def create_school_service(db: Session, data: SchoolCreate, user: User):
    # Every authenticated Tutor user may open a school profile. It starts
    # unverified and becomes an isolated workspace immediately. Platform
    # verification remains separate from workspace creation.
    payload = data.model_copy(update={"slug": data.slug or _slugify(data.name)})

    school = school_crud.create_school(db, payload)
    existing_memberships = (
        db.query(SchoolMembership)
        .filter(SchoolMembership.user_id == user.id, SchoolMembership.is_active.is_(True))
        .count()
    )
    membership = SchoolMembership(
        user_id=user.id,
        school_id=school.id,
        role="school_admin",
        title="School Administrator",
        is_active=True,
        is_default=existing_memberships == 0,
    )
    db.add(membership)

    # Compatibility bridge for older modules while they are migrated to the
    # active-school context.
    if user.school_id is None:
        user.school_id = school.id

    db.commit()
    db.refresh(school)
    return school


def get_schools_service(db: Session, user: User):
    if _role_value(user) == "super_admin":
        return school_crud.get_schools(db)

    school_ids = [
        row.school_id
        for row in db.query(SchoolMembership)
        .filter(
            SchoolMembership.user_id == user.id,
            SchoolMembership.is_active.is_(True),
        )
        .all()
    ]
    if user.school_id is not None and user.school_id not in school_ids:
        school_ids.append(user.school_id)
    if not school_ids:
        return []
    return db.query(School).filter(School.id.in_(school_ids), School.is_active.is_(True)).order_by(School.name.asc()).all()


def get_school_service(db: Session, school_id: UUID, user: User):
    school = school_crud.get_school(db, school_id)
    if not school:
        return None
    if _role_value(user) == "super_admin":
        return school
    if _membership(db, user, school_id) is not None or user.school_id == school_id:
        return school
    raise PermissionError("Not allowed to access this school workspace")


def update_school_service(db: Session, school_id: UUID, data: SchoolUpdate, user: User):
    school = get_school_service(db, school_id, user)
    is_platform_admin = _role_value(user) == "super_admin"
    membership = _membership(db, user, school_id)
    workspace_role = membership.role if membership is not None else _role_value(user)

    if not is_platform_admin and workspace_role not in {"school_admin", "principal"}:
        raise PermissionError("Only school administration can update the school profile")

    if not is_platform_admin and any(
        field in data.model_fields_set
        for field in {"is_registered", "is_active", "certificate_number"}
    ):
        raise PermissionError("Only platform administration can change school verification status")

    return school_crud.update_school(db, school, data)


def delete_school_service(db: Session, school_id: UUID, user: User):
    if _role_value(user) != "super_admin":
        raise PermissionError("Only platform administration can delete a school")
    school = get_school_service(db, school_id, user)
    return school_crud.delete_school(db, school)
