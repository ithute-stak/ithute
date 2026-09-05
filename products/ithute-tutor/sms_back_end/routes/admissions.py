from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import ParentStudent, Student, StudentEnrollment
from database.multi_tenant_school_management.models.tutor_completion import AdmissionApplication, StudentDocument
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/admissions", tags=["Admissions"])
MANAGERS = ("school_admin", "principal", "vice_principal", "registrar", "admissions_officer")


class AdmissionCreate(BaseModel):
    applicant_first_name: str = Field(min_length=1, max_length=120)
    applicant_last_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date | None = None
    guardian_name: str = Field(min_length=1, max_length=200)
    guardian_email: str | None = None
    guardian_phone: str | None = None
    desired_grade_id: UUID | None = None
    desired_class_id: UUID | None = None
    notes: str | None = None


class AdmissionDecision(BaseModel):
    status: Literal["under_review", "accepted", "waitlisted", "rejected", "enrolled"]
    notes: str | None = None


class DocumentCreate(BaseModel):
    document_type: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=200)
    storage_url: str = Field(min_length=3)


class DocumentReview(BaseModel):
    status: Literal["pending", "verified", "rejected"]


def _student_belongs_to_school(db: Session, school_id: UUID, student_id: UUID) -> bool:
    return db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == school_id,
        StudentEnrollment.student_id == student_id,
    ).first() is not None


def _assert_document_access(db: Session, context: SchoolContext, student_id: UUID) -> None:
    if not _student_belongs_to_school(db, context.school_id, student_id):
        raise HTTPException(status_code=404, detail="student record not found in this school")
    if context.is_platform_admin or context.role in MANAGERS:
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
    raise HTTPException(status_code=403, detail="not permitted to view this learner's documents")


@router.get("/applications")
def list_applications(
    status: str | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MANAGERS)),
):
    query = db.query(AdmissionApplication).filter(AdmissionApplication.school_id == context.school_id)
    if status:
        query = query.filter(AdmissionApplication.status == status)
    return query.order_by(AdmissionApplication.created_at.desc()).all()


@router.post("/applications")
def create_application(
    payload: AdmissionCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    application = AdmissionApplication(school_id=context.school_id, **payload.model_dump())
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.put("/applications/{application_id}/decision")
def decide_application(
    application_id: UUID,
    payload: AdmissionDecision,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MANAGERS)),
):
    application = db.query(AdmissionApplication).filter(
        AdmissionApplication.id == application_id,
        AdmissionApplication.school_id == context.school_id,
    ).first()
    if not application:
        raise HTTPException(status_code=404, detail="admission application not found")
    application.status = payload.status
    application.notes = payload.notes if payload.notes is not None else application.notes
    application.reviewed_by = context.user_id
    application.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(application)
    return application


@router.get("/students/{student_id}/documents")
def list_documents(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _assert_document_access(db, context, student_id)
    return db.query(StudentDocument).filter(
        StudentDocument.school_id == context.school_id,
        StudentDocument.student_id == student_id,
    ).order_by(StudentDocument.created_at.desc()).all()


@router.post("/students/{student_id}/documents")
def add_document(
    student_id: UUID,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MANAGERS)),
):
    if not db.get(Student, student_id) or not _student_belongs_to_school(db, context.school_id, student_id):
        raise HTTPException(status_code=404, detail="student not found in this school")
    document = StudentDocument(school_id=context.school_id, student_id=student_id, **payload.model_dump())
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.put("/documents/{document_id}/review")
def review_document(
    document_id: UUID,
    payload: DocumentReview,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MANAGERS)),
):
    document = db.query(StudentDocument).filter(
        StudentDocument.id == document_id,
        StudentDocument.school_id == context.school_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="student document not found")
    document.status = payload.status
    if payload.status == "verified":
        document.verified_by = context.user_id
        document.verified_at = datetime.now(timezone.utc)
    else:
        document.verified_by = None
        document.verified_at = None
    db.commit()
    db.refresh(document)
    return document
