from datetime import date, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models.academic_core import (
    AcademicTerm,
    AcademicYear,
    Assessment,
    AssessmentResult,
    TeachingAssignment,
    TimetableEntry,
)
from database.multi_tenant_school_management.models import (
    Class,
    SchoolClass,
    SchoolGradeSubject,
    Student,
    StudentEnrollment,
    Subject,
    Teacher,
)
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/academic", tags=["Academic Core"])

ACADEMIC_MANAGERS = ("school_admin", "principal", "vice_principal")
ACADEMIC_WRITERS = ("school_admin", "principal", "vice_principal", "teacher", "class_teacher")


class AcademicYearCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    start_date: date
    end_date: date
    is_current: bool = False


class AcademicYearRead(AcademicYearCreate):
    id: UUID
    school_id: UUID
    is_closed: bool
    model_config = ConfigDict(from_attributes=True)


class AcademicTermCreate(BaseModel):
    academic_year_id: UUID
    name: str = Field(min_length=2, max_length=80)
    sequence: int = Field(ge=1, le=20)
    start_date: date
    end_date: date
    is_current: bool = False


class AcademicTermRead(AcademicTermCreate):
    id: UUID
    school_id: UUID
    is_closed: bool
    model_config = ConfigDict(from_attributes=True)


class TeachingAssignmentCreate(BaseModel):
    academic_year_id: UUID
    term_id: UUID | None = None
    teacher_id: UUID
    class_id: UUID
    subject_id: UUID
    is_class_teacher: bool = False


class TeachingAssignmentRead(TeachingAssignmentCreate):
    id: UUID
    school_id: UUID
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class TimetableEntryCreate(BaseModel):
    academic_year_id: UUID
    term_id: UUID
    teaching_assignment_id: UUID
    day_of_week: int = Field(ge=1, le=7)
    start_time: time
    end_time: time
    room: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=500)


class TimetableEntryRead(TimetableEntryCreate):
    id: UUID
    school_id: UUID
    model_config = ConfigDict(from_attributes=True)


class AssessmentCreate(BaseModel):
    academic_year_id: UUID
    term_id: UUID
    class_id: UUID
    subject_id: UUID
    teacher_id: UUID | None = None
    title: str = Field(min_length=2, max_length=160)
    assessment_type: Literal["assignment", "quiz", "test", "project", "practical", "exam", "other"] = "test"
    description: str | None = None
    assessment_date: date
    max_score: Decimal = Field(gt=0)
    weight: Decimal = Field(default=Decimal("1"), gt=0)
    is_published: bool = False


class AssessmentRead(AssessmentCreate):
    id: UUID
    school_id: UUID
    is_locked: bool
    model_config = ConfigDict(from_attributes=True)


class ResultUpsert(BaseModel):
    student_id: UUID
    score: Decimal | None = Field(default=None, ge=0)
    is_absent: bool = False
    is_excused: bool = False
    remarks: str | None = Field(default=None, max_length=500)


class AssessmentResultRead(ResultUpsert):
    id: UUID
    school_id: UUID
    assessment_id: UUID
    model_config = ConfigDict(from_attributes=True)


def _year(db: Session, school_id: UUID, year_id: UUID) -> AcademicYear:
    item = db.query(AcademicYear).filter(AcademicYear.id == year_id, AcademicYear.school_id == school_id).first()
    if item is None:
        raise HTTPException(404, "Academic year not found in this school")
    return item


def _term(db: Session, school_id: UUID, term_id: UUID) -> AcademicTerm:
    item = db.query(AcademicTerm).filter(AcademicTerm.id == term_id, AcademicTerm.school_id == school_id).first()
    if item is None:
        raise HTTPException(404, "Academic term not found in this school")
    return item


def _school_class(db: Session, school_id: UUID, class_id: UUID) -> Class:
    link = db.query(SchoolClass).filter(SchoolClass.school_id == school_id, SchoolClass.class_id == class_id).first()
    if link is None:
        raise HTTPException(404, "Class is not enabled in this school")
    classroom = db.get(Class, class_id)
    if classroom is None:
        raise HTTPException(404, "Class not found")
    return classroom


def _school_subject(db: Session, school_id: UUID, classroom: Class, subject_id: UUID) -> Subject:
    link = (
        db.query(SchoolGradeSubject)
        .filter(
            SchoolGradeSubject.school_id == school_id,
            SchoolGradeSubject.grade_id == classroom.grade_id,
            SchoolGradeSubject.subject_id == subject_id,
        )
        .first()
    )
    if link is None:
        raise HTTPException(404, "Subject is not offered for this class grade in this school")
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(404, "Subject not found")
    return subject


def _teacher(db: Session, school_id: UUID, teacher_id: UUID) -> Teacher:
    item = db.query(Teacher).filter(Teacher.id == teacher_id, Teacher.school_id == school_id).first()
    if item is None:
        raise HTTPException(404, "Teacher not found in this school")
    return item


def _enrolled(db: Session, school_id: UUID, student_id: UUID, class_id: UUID | None = None) -> StudentEnrollment:
    query = db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == school_id,
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.is_current.is_(True),
    )
    if class_id is not None:
        query = query.filter(StudentEnrollment.class_id == class_id)
    enrollment = query.first()
    if enrollment is None:
        raise HTTPException(404, "Student is not currently enrolled in this school/class")
    return enrollment


@router.post("/years", response_model=AcademicYearRead, status_code=201)
def create_academic_year(
    payload: AcademicYearCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_MANAGERS)),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "Academic year end date must be after start date")
    if payload.is_current:
        db.query(AcademicYear).filter(AcademicYear.school_id == context.school_id).update({AcademicYear.is_current: False})
    item = AcademicYear(school_id=context.school_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/years", response_model=list[AcademicYearRead])
def list_academic_years(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return db.query(AcademicYear).filter(AcademicYear.school_id == context.school_id).order_by(AcademicYear.start_date.desc()).all()


@router.post("/years/{year_id}/close", response_model=AcademicYearRead)
def close_academic_year(
    year_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_MANAGERS)),
):
    item = _year(db, context.school_id, year_id)
    item.is_closed = True
    item.is_current = False
    db.query(AcademicTerm).filter(AcademicTerm.school_id == context.school_id, AcademicTerm.academic_year_id == year_id).update({AcademicTerm.is_closed: True, AcademicTerm.is_current: False})
    db.commit()
    db.refresh(item)
    return item


@router.post("/terms", response_model=AcademicTermRead, status_code=201)
def create_academic_term(
    payload: AcademicTermCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_MANAGERS)),
):
    year = _year(db, context.school_id, payload.academic_year_id)
    if year.is_closed:
        raise HTTPException(409, "Academic year is closed")
    if payload.start_date < year.start_date or payload.end_date > year.end_date or payload.end_date < payload.start_date:
        raise HTTPException(400, "Term dates must fall inside the academic year")
    if payload.is_current:
        db.query(AcademicTerm).filter(AcademicTerm.school_id == context.school_id).update({AcademicTerm.is_current: False})
        year.is_current = True
    item = AcademicTerm(school_id=context.school_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/terms", response_model=list[AcademicTermRead])
def list_terms(
    academic_year_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(AcademicTerm).filter(AcademicTerm.school_id == context.school_id)
    if academic_year_id:
        query = query.filter(AcademicTerm.academic_year_id == academic_year_id)
    return query.order_by(AcademicTerm.start_date.desc(), AcademicTerm.sequence.asc()).all()


@router.post("/assignments", response_model=TeachingAssignmentRead, status_code=201)
def create_teaching_assignment(
    payload: TeachingAssignmentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_MANAGERS)),
):
    year = _year(db, context.school_id, payload.academic_year_id)
    if year.is_closed:
        raise HTTPException(409, "Academic year is closed")
    if payload.term_id:
        term = _term(db, context.school_id, payload.term_id)
        if term.academic_year_id != year.id:
            raise HTTPException(400, "Term does not belong to the academic year")
    classroom = _school_class(db, context.school_id, payload.class_id)
    _school_subject(db, context.school_id, classroom, payload.subject_id)
    _teacher(db, context.school_id, payload.teacher_id)
    item = TeachingAssignment(school_id=context.school_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/assignments", response_model=list[TeachingAssignmentRead])
def list_teaching_assignments(
    academic_year_id: UUID | None = None,
    term_id: UUID | None = None,
    teacher_id: UUID | None = None,
    class_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(TeachingAssignment).filter(TeachingAssignment.school_id == context.school_id, TeachingAssignment.is_active.is_(True))
    for column, value in ((TeachingAssignment.academic_year_id, academic_year_id), (TeachingAssignment.term_id, term_id), (TeachingAssignment.teacher_id, teacher_id), (TeachingAssignment.class_id, class_id)):
        if value:
            query = query.filter(column == value)
    return query.order_by(TeachingAssignment.created_at.desc()).all()


@router.post("/timetable", response_model=TimetableEntryRead, status_code=201)
def create_timetable_entry(
    payload: TimetableEntryCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_MANAGERS)),
):
    if payload.end_time <= payload.start_time:
        raise HTTPException(400, "Timetable end time must be after start time")
    year = _year(db, context.school_id, payload.academic_year_id)
    term = _term(db, context.school_id, payload.term_id)
    if year.is_closed or term.is_closed:
        raise HTTPException(409, "Academic period is closed")
    if term.academic_year_id != year.id:
        raise HTTPException(400, "Term does not belong to the academic year")
    assignment = db.query(TeachingAssignment).filter(TeachingAssignment.id == payload.teaching_assignment_id, TeachingAssignment.school_id == context.school_id).first()
    if assignment is None:
        raise HTTPException(404, "Teaching assignment not found in this school")
    if assignment.academic_year_id != year.id or (assignment.term_id and assignment.term_id != term.id):
        raise HTTPException(400, "Teaching assignment does not belong to this academic period")
    overlap = (
        db.query(TimetableEntry)
        .join(TeachingAssignment, TeachingAssignment.id == TimetableEntry.teaching_assignment_id)
        .filter(
            TimetableEntry.school_id == context.school_id,
            TimetableEntry.term_id == term.id,
            TimetableEntry.day_of_week == payload.day_of_week,
            TimetableEntry.start_time < payload.end_time,
            TimetableEntry.end_time > payload.start_time,
            or_(TeachingAssignment.teacher_id == assignment.teacher_id, TeachingAssignment.class_id == assignment.class_id),
        )
        .first()
    )
    if overlap:
        raise HTTPException(409, "Teacher or class already has a timetable entry in this time slot")
    item = TimetableEntry(school_id=context.school_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/timetable", response_model=list[TimetableEntryRead])
def list_timetable(
    term_id: UUID | None = None,
    class_id: UUID | None = None,
    teacher_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(TimetableEntry).join(TeachingAssignment).filter(TimetableEntry.school_id == context.school_id)
    if term_id:
        query = query.filter(TimetableEntry.term_id == term_id)
    if class_id:
        query = query.filter(TeachingAssignment.class_id == class_id)
    if teacher_id:
        query = query.filter(TeachingAssignment.teacher_id == teacher_id)
    return query.order_by(TimetableEntry.day_of_week.asc(), TimetableEntry.start_time.asc()).all()


@router.post("/assessments", response_model=AssessmentRead, status_code=201)
def create_assessment(
    payload: AssessmentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_WRITERS)),
):
    year = _year(db, context.school_id, payload.academic_year_id)
    term = _term(db, context.school_id, payload.term_id)
    if year.is_closed or term.is_closed:
        raise HTTPException(409, "Academic period is closed")
    if term.academic_year_id != year.id:
        raise HTTPException(400, "Term does not belong to the academic year")
    classroom = _school_class(db, context.school_id, payload.class_id)
    _school_subject(db, context.school_id, classroom, payload.subject_id)
    if payload.teacher_id:
        _teacher(db, context.school_id, payload.teacher_id)
    item = Assessment(school_id=context.school_id, **payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/assessments", response_model=list[AssessmentRead])
def list_assessments(
    term_id: UUID | None = None,
    class_id: UUID | None = None,
    subject_id: UUID | None = None,
    published_only: bool = False,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(Assessment).filter(Assessment.school_id == context.school_id)
    for column, value in ((Assessment.term_id, term_id), (Assessment.class_id, class_id), (Assessment.subject_id, subject_id)):
        if value:
            query = query.filter(column == value)
    if published_only:
        query = query.filter(Assessment.is_published.is_(True))
    return query.order_by(Assessment.assessment_date.desc()).all()


@router.put("/assessments/{assessment_id}/results", response_model=AssessmentResultRead)
def upsert_assessment_result(
    assessment_id: UUID,
    payload: ResultUpsert,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_WRITERS)),
):
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id, Assessment.school_id == context.school_id).first()
    if assessment is None:
        raise HTTPException(404, "Assessment not found in this school")
    if assessment.is_locked:
        raise HTTPException(409, "Assessment results are locked")
    _enrolled(db, context.school_id, payload.student_id, assessment.class_id)
    if payload.score is not None and payload.score > assessment.max_score:
        raise HTTPException(400, "Score cannot exceed assessment maximum")
    item = db.query(AssessmentResult).filter(AssessmentResult.assessment_id == assessment.id, AssessmentResult.student_id == payload.student_id).first()
    if item is None:
        item = AssessmentResult(school_id=context.school_id, assessment_id=assessment.id, **payload.model_dump())
        db.add(item)
    else:
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.post("/assessments/{assessment_id}/publish", response_model=AssessmentRead)
def publish_assessment(
    assessment_id: UUID,
    lock: bool = Query(default=False),
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ACADEMIC_MANAGERS)),
):
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id, Assessment.school_id == context.school_id).first()
    if assessment is None:
        raise HTTPException(404, "Assessment not found in this school")
    assessment.is_published = True
    if lock:
        assessment.is_locked = True
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/report-cards/{student_id}")
def report_card(
    student_id: UUID,
    term_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    term = _term(db, context.school_id, term_id)
    enrollment = _enrolled(db, context.school_id, student_id)
    student = db.get(Student, student_id)
    rows = (
        db.query(AssessmentResult, Assessment, Subject)
        .join(Assessment, Assessment.id == AssessmentResult.assessment_id)
        .join(Subject, Subject.id == Assessment.subject_id)
        .filter(
            AssessmentResult.school_id == context.school_id,
            AssessmentResult.student_id == student_id,
            Assessment.term_id == term.id,
            Assessment.is_published.is_(True),
        )
        .all()
    )
    subjects: dict[str, dict] = {}
    for result, assessment, subject in rows:
        bucket = subjects.setdefault(str(subject.id), {"subject_id": str(subject.id), "subject": subject.name, "earned": Decimal("0"), "possible": Decimal("0"), "items": 0})
        if result.score is not None and not result.is_absent:
            weight = Decimal(str(assessment.weight))
            bucket["earned"] += (Decimal(str(result.score)) / Decimal(str(assessment.max_score))) * weight
            bucket["possible"] += weight
            bucket["items"] += 1
    subject_results = []
    total = Decimal("0")
    count = 0
    for bucket in subjects.values():
        percentage = (bucket["earned"] / bucket["possible"] * Decimal("100")) if bucket["possible"] else None
        if percentage is not None:
            total += percentage
            count += 1
        subject_results.append({
            "subject_id": bucket["subject_id"],
            "subject": bucket["subject"],
            "percentage": round(float(percentage), 2) if percentage is not None else None,
            "assessments_count": bucket["items"],
        })
    overall = round(float(total / count), 2) if count else None
    return {
        "school_id": str(context.school_id),
        "student_id": str(student_id),
        "student": getattr(getattr(student, "user", None), "username", None) if student else None,
        "class_id": str(enrollment.class_id) if enrollment.class_id else None,
        "academic_year_id": str(term.academic_year_id),
        "term_id": str(term.id),
        "term": term.name,
        "subjects": subject_results,
        "overall_percentage": overall,
    }


@router.get("/overview")
def academic_overview(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    current_year = db.query(AcademicYear).filter(AcademicYear.school_id == context.school_id, AcademicYear.is_current.is_(True)).first()
    current_term = db.query(AcademicTerm).filter(AcademicTerm.school_id == context.school_id, AcademicTerm.is_current.is_(True)).first()
    return {
        "school_id": str(context.school_id),
        "current_year": AcademicYearRead.model_validate(current_year).model_dump(mode="json") if current_year else None,
        "current_term": AcademicTermRead.model_validate(current_term).model_dump(mode="json") if current_term else None,
        "teaching_assignments": db.query(TeachingAssignment).filter(TeachingAssignment.school_id == context.school_id, TeachingAssignment.is_active.is_(True)).count(),
        "assessments": db.query(Assessment).filter(Assessment.school_id == context.school_id).count(),
        "published_assessments": db.query(Assessment).filter(Assessment.school_id == context.school_id, Assessment.is_published.is_(True)).count(),
    }
