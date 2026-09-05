from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import (
    Person,
    SchoolClass,
    SchoolMembership,
    Student,
    StudentEnrollment,
    User,
)
from database.multi_tenant_school_management.models.academic_core import AcademicTerm, AcademicYear
from database.multi_tenant_school_management.models.enum.user_role import UserRole
from database.multi_tenant_school_management.schemas.student import (
    StudentAdmissionNumberResponse,
    StudentCreate,
    StudentRead,
)
from database.session import get_db
from routes.finance_management.service.payment_component.inner_components.get_student_statement import get_student_statement
from routes.service.student_number import StudentAdmissionNumberService
from utils.auth.password_hash_verify import hash_password
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/students", tags=["Students"])

STUDENT_MANAGERS = ("school_admin", "principal", "vice_principal", "registrar", "admissions_officer")


class EnrollmentCreate(BaseModel):
    class_id: UUID
    start_date: date = Field(default_factory=date.today)
    academic_year_id: UUID | None = None
    term_id: UUID | None = None


class EnrollmentClose(BaseModel):
    effective_date: date = Field(default_factory=date.today)
    status: str = Field(pattern="^(withdrawn|transferred|graduated|completed)$")
    reason: str | None = Field(default=None, max_length=500)
    transfer_destination: str | None = Field(default=None, max_length=255)


def _students_for_school(db: Session, school_id: UUID):
    return (
        db.query(Student)
        .outerjoin(StudentEnrollment, StudentEnrollment.student_id == Student.id)
        .filter(
            StudentEnrollment.school_id == school_id,
            StudentEnrollment.is_current.is_(True),
        )
        .distinct()
    )


def _student_for_school(db: Session, student_id: UUID, school_id: UUID) -> Student | None:
    return _students_for_school(db, school_id).filter(Student.id == student_id).first()


def _enabled_class(db: Session, school_id: UUID, class_id: UUID):
    link = db.query(SchoolClass).filter(SchoolClass.school_id == school_id, SchoolClass.class_id == class_id).first()
    if link is None:
        raise HTTPException(404, "Class is not enabled in this school")
    return link


def _resolve_period(db: Session, school_id: UUID, start_date: date, year_id: UUID | None, term_id: UUID | None):
    year = None
    term = None
    if year_id:
        year = db.query(AcademicYear).filter(AcademicYear.id == year_id, AcademicYear.school_id == school_id).first()
        if year is None:
            raise HTTPException(404, "Academic year not found in this school")
    else:
        year = db.query(AcademicYear).filter(
            AcademicYear.school_id == school_id,
            AcademicYear.start_date <= start_date,
            AcademicYear.end_date >= start_date,
        ).first()
    if term_id:
        term = db.query(AcademicTerm).filter(AcademicTerm.id == term_id, AcademicTerm.school_id == school_id).first()
        if term is None:
            raise HTTPException(404, "Academic term not found in this school")
        if year and term.academic_year_id != year.id:
            raise HTTPException(400, "Term does not belong to the selected academic year")
    else:
        term = db.query(AcademicTerm).filter(
            AcademicTerm.school_id == school_id,
            AcademicTerm.start_date <= start_date,
            AcademicTerm.end_date >= start_date,
        ).first()
    return year, term


def _open_enrollment(db: Session, student_id: UUID, school_id: UUID, payload: EnrollmentCreate):
    _enabled_class(db, school_id, payload.class_id)
    existing = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.school_id == school_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    if existing:
        raise HTTPException(409, "Learner already has an active enrolment in this school")
    year, term = _resolve_period(db, school_id, payload.start_date, payload.academic_year_id, payload.term_id)
    enrollment = StudentEnrollment(
        student_id=student_id,
        school_id=school_id,
        class_id=payload.class_id,
        start_date=payload.start_date,
        academic_year_id=year.id if year else None,
        term_id=term.id if term else None,
        academic_year=year.name if year else None,
        term=term.name if term else None,
        status="active",
        is_current=True,
    )
    db.add(enrollment)
    return enrollment


@router.get("/generate-admission-number", response_model=StudentAdmissionNumberResponse)
def generate_student_admission_number(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    try:
        admission_number = StudentAdmissionNumberService.generate_admission_number(db=db)
        return {"admission_number": admission_number}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/", response_model=StudentRead, status_code=201)
def create_student(
    payload: StudentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*STUDENT_MANAGERS)),
):
    if db.query(User).filter(User.email == payload.user.email).first():
        raise HTTPException(409, "This email already has a Tutor identity; enrol the existing learner instead")
    _enabled_class(db, context.school_id, payload.class_id)

    user_payload = payload.user.model_dump(exclude={"person", "password", "school_id", "role"})
    user = User(
        **user_payload,
        school_id=context.school_id,
        role=UserRole.student,
        password=hash_password(payload.user.password) if payload.user.password else None,
    )
    db.add(user)
    db.flush()
    db.add(Person(**payload.user.person.model_dump(), id=user.id))
    db.flush()

    student = Student(id=user.id, admission_number=payload.admission_number, class_id=payload.class_id)
    db.add(student)
    db.flush()
    db.add(SchoolMembership(
        user_id=user.id,
        school_id=context.school_id,
        role="student",
        title="Student",
        is_active=True,
        is_default=True,
    ))
    _open_enrollment(db, student.id, context.school_id, EnrollmentCreate(class_id=payload.class_id))
    db.commit()
    db.refresh(student)
    return student


@router.post("/{student_id}/enroll", status_code=201)
def enroll_existing_learner(
    student_id: UUID,
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*STUDENT_MANAGERS)),
):
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(404, "Learner identity not found")
    enrollment = _open_enrollment(db, student.id, context.school_id, payload)
    membership = db.query(SchoolMembership).filter(
        SchoolMembership.user_id == student.id,
        SchoolMembership.school_id == context.school_id,
    ).first()
    if membership is None:
        db.add(SchoolMembership(user_id=student.id, school_id=context.school_id, role="student", title="Student", is_active=True, is_default=False))
    else:
        membership.is_active = True
        membership.role = "student"
    student.class_id = payload.class_id
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.post("/{student_id}/close-enrollment")
def close_student_enrollment(
    student_id: UUID,
    payload: EnrollmentClose,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*STUDENT_MANAGERS)),
):
    enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    if enrollment is None:
        raise HTTPException(404, "Active enrolment not found in this school")
    if enrollment.start_date and payload.effective_date < enrollment.start_date:
        raise HTTPException(400, "Closure date cannot be before enrolment start date")
    enrollment.end_date = payload.effective_date
    enrollment.status = payload.status
    enrollment.withdrawal_reason = payload.reason
    enrollment.transfer_destination = payload.transfer_destination
    enrollment.is_current = False
    membership = db.query(SchoolMembership).filter(
        SchoolMembership.user_id == student_id,
        SchoolMembership.school_id == context.school_id,
    ).first()
    if membership:
        membership.is_active = False
    db.commit()
    db.refresh(enrollment)
    return enrollment


@router.get("/{student_id}/enrollment-history")
def enrollment_history(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    # Schools see only their own historical relationship with the learner.
    return db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.school_id == context.school_id,
    ).order_by(StudentEnrollment.start_date.desc()).all()


@router.get("/", response_model=list[StudentRead])
def read_students(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return _students_for_school(db, context.school_id).all()


@router.get("/{student_id}", response_model=StudentRead)
def get_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    student = _student_for_school(db, student_id, context.school_id)
    if not student:
        raise HTTPException(404, "Student not found in this school")
    return student


@router.delete("/{student_id}")
def delete_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("super_admin")),
):
    if not context.is_platform_admin:
        raise HTTPException(status_code=403, detail="withdraw the school enrolment instead of deleting the learner")
    student = db.get(Student, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    db.delete(student)
    db.commit()
    return {"message": "Learner record deleted by platform administration"}


@router.get("/student/{student_id}/statement")
def student_statement(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    student = _student_for_school(db, student_id, context.school_id)
    if not student:
        raise HTTPException(404, "Student not found in this school")
    return get_student_statement(db=db, student_id=str(student_id))
