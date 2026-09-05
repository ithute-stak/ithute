from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import Grade, SchoolGradeSubject, Subject
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/academic/curriculum", tags=["Academic Curriculum"])


class CurriculumOfferingCreate(BaseModel):
    grade_id: UUID
    subject_id: UUID
    daily_credit_hours: int = Field(default=1, ge=0, le=24)
    weekly_credit_hours: int = Field(default=5, ge=0, le=168)
    is_core: bool = True


def _serialize(link: SchoolGradeSubject):
    return {
        "id": str(link.id),
        "school_id": str(link.school_id),
        "grade_id": str(link.grade_id),
        "grade": link.grade.name if link.grade else None,
        "subject_id": str(link.subject_id),
        "subject": link.subject.name if link.subject else None,
        "description": link.subject.description if link.subject else None,
        "daily_credit_hours": link.daily_credit_hours,
        "weekly_credit_hours": link.weekly_credit_hours,
        "is_core": bool(link.is_core),
    }


@router.get("/catalog")
def curriculum_catalog(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    # Catalog is shared reference data; the response intentionally contains no
    # other school's curriculum choices or operational data.
    grades = db.query(Grade).order_by(Grade.name.asc()).all()
    subjects = db.query(Subject).order_by(Subject.name.asc()).all()
    return {
        "school_id": str(context.school_id),
        "grades": [{"id": str(item.id), "name": item.name} for item in grades],
        "subjects": [
            {"id": str(item.id), "name": item.name, "description": item.description}
            for item in subjects
        ],
    }


@router.get("")
def list_curriculum(
    grade_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(SchoolGradeSubject).filter(SchoolGradeSubject.school_id == context.school_id)
    if grade_id:
        query = query.filter(SchoolGradeSubject.grade_id == grade_id)
    return [_serialize(item) for item in query.order_by(SchoolGradeSubject.grade_id.asc()).all()]


@router.post("", status_code=201)
def add_curriculum_offering(
    payload: CurriculumOfferingCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "principal", "vice_principal")),
):
    if db.get(Grade, payload.grade_id) is None:
        raise HTTPException(404, "Grade not found in the Tutor catalog")
    if db.get(Subject, payload.subject_id) is None:
        raise HTTPException(404, "Subject not found in the Tutor catalog")
    existing = db.query(SchoolGradeSubject).filter(
        SchoolGradeSubject.school_id == context.school_id,
        SchoolGradeSubject.grade_id == payload.grade_id,
        SchoolGradeSubject.subject_id == payload.subject_id,
    ).first()
    if existing:
        raise HTTPException(409, "Subject is already offered for this grade")
    item = SchoolGradeSubject(school_id=context.school_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.put("/{offering_id}")
def update_curriculum_offering(
    offering_id: UUID,
    payload: CurriculumOfferingCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "principal", "vice_principal")),
):
    item = db.query(SchoolGradeSubject).filter(
        SchoolGradeSubject.id == offering_id,
        SchoolGradeSubject.school_id == context.school_id,
    ).first()
    if item is None:
        raise HTTPException(404, "Curriculum offering not found in this school")
    item.grade_id = payload.grade_id
    item.subject_id = payload.subject_id
    item.daily_credit_hours = payload.daily_credit_hours
    item.weekly_credit_hours = payload.weekly_credit_hours
    item.is_core = payload.is_core
    db.commit()
    db.refresh(item)
    return _serialize(item)


@router.delete("/{offering_id}")
def remove_curriculum_offering(
    offering_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "principal", "vice_principal")),
):
    item = db.query(SchoolGradeSubject).filter(
        SchoolGradeSubject.id == offering_id,
        SchoolGradeSubject.school_id == context.school_id,
    ).first()
    if item is None:
        raise HTTPException(404, "Curriculum offering not found in this school")
    db.delete(item)
    db.commit()
    return {"message": "Subject removed from this school's curriculum"}
