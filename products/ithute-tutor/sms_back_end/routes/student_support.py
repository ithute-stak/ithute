from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import ParentStudent, StudentEnrollment
from database.multi_tenant_school_management.models.tutor_completion import DisciplineIncident, StudentHealthRecord
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/student-support", tags=["Student Support"])
SUPPORT_STAFF = ("school_admin", "principal", "vice_principal", "teacher", "class_teacher", "counsellor", "nurse")
HEALTH_STAFF = ("school_admin", "principal", "vice_principal", "nurse")


class IncidentCreate(BaseModel):
    student_id: UUID
    category: str = Field(min_length=2, max_length=80)
    severity: str = Field(default="low", max_length=24)
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=2)
    occurred_on: date
    action_taken: str | None = None


class HealthUpdate(BaseModel):
    allergies: str | None = None
    conditions: str | None = None
    medications: str | None = None
    emergency_notes: str | None = None
    emergency_contact: str | None = None


def _student_belongs_to_school(db: Session, school_id: UUID, student_id: UUID) -> bool:
    return db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == school_id,
        StudentEnrollment.student_id == student_id,
    ).first() is not None


def _assert_discipline_access(db: Session, context: SchoolContext, student_id: UUID) -> None:
    if not _student_belongs_to_school(db, context.school_id, student_id):
        raise HTTPException(status_code=404, detail="student record not found in this school")
    if context.is_platform_admin or context.role in SUPPORT_STAFF:
        return
    if context.role == "student" and context.user_id == student_id:
        return
    if context.role == "parent":
        linked = db.query(ParentStudent).filter(
            ParentStudent.parent_id == context.user_id,
            ParentStudent.student_id == student_id,
        ).first()
        if linked:
            return
    raise HTTPException(status_code=403, detail="not permitted to view this learner's discipline record")


@router.get("/students/{student_id}/discipline")
def discipline_history(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _assert_discipline_access(db, context, student_id)
    return db.query(DisciplineIncident).filter(
        DisciplineIncident.school_id == context.school_id,
        DisciplineIncident.student_id == student_id,
    ).order_by(DisciplineIncident.occurred_on.desc(), DisciplineIncident.created_at.desc()).all()


@router.post("/discipline")
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*SUPPORT_STAFF)),
):
    if not _student_belongs_to_school(db, context.school_id, payload.student_id):
        raise HTTPException(status_code=404, detail="student not found in this school")
    incident = DisciplineIncident(school_id=context.school_id, **payload.model_dump())
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("/students/{student_id}/health")
def get_health_record(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*HEALTH_STAFF)),
):
    if not _student_belongs_to_school(db, context.school_id, student_id):
        raise HTTPException(status_code=404, detail="student not found in this school")
    return db.query(StudentHealthRecord).filter(
        StudentHealthRecord.school_id == context.school_id,
        StudentHealthRecord.student_id == student_id,
    ).first()


@router.put("/students/{student_id}/health")
def update_health_record(
    student_id: UUID,
    payload: HealthUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*HEALTH_STAFF)),
):
    if not _student_belongs_to_school(db, context.school_id, student_id):
        raise HTTPException(status_code=404, detail="student not found in this school")
    record = db.query(StudentHealthRecord).filter(
        StudentHealthRecord.school_id == context.school_id,
        StudentHealthRecord.student_id == student_id,
    ).first()
    if not record:
        record = StudentHealthRecord(school_id=context.school_id, student_id=student_id)
        db.add(record)
    for key, value in payload.model_dump().items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record
