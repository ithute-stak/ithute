from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import SchoolClass
from database.multi_tenant_school_management.schemas.school_class import SchoolClassCreate
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/school-classes", tags=["School Classes"])


@router.post("")
def assign_class(
    payload: SchoolClassCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "principal", "vice_principal", "registrar")),
):
    data = payload.model_dump(exclude={"school_id"})
    existing = (
        db.query(SchoolClass)
        .filter(
            SchoolClass.school_id == context.school_id,
            SchoolClass.class_id == data["class_id"],
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Class is already assigned to this school")
    school_class = SchoolClass(**data, school_id=context.school_id)
    db.add(school_class)
    db.commit()
    db.refresh(school_class)
    return school_class


@router.get("")
def get_school_classes(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return db.query(SchoolClass).filter(SchoolClass.school_id == context.school_id).all()


@router.get("/school/{school_id}")
def get_school_classes_compat(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    if school_id != context.school_id and not context.is_platform_admin:
        raise HTTPException(status_code=403, detail="Cannot access another school's classes")
    return db.query(SchoolClass).filter(SchoolClass.school_id == school_id).all()


@router.patch("/{school_class_id}/capacity")
def update_capacity(
    school_class_id: UUID,
    capacity: int,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "principal", "vice_principal", "registrar")),
):
    if capacity < 1:
        raise HTTPException(status_code=400, detail="Capacity must be at least 1")
    school_class = (
        db.query(SchoolClass)
        .filter(
            SchoolClass.id == school_class_id,
            SchoolClass.school_id == context.school_id,
        )
        .first()
    )
    if not school_class:
        raise HTTPException(status_code=404, detail="School class not found")
    school_class.capacity = capacity
    db.commit()
    db.refresh(school_class)
    return school_class
