from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import StudentAttendance, StudentEnrollment
from database.multi_tenant_school_management.models.academic_core import AcademicTerm, AcademicYear
from database.multi_tenant_school_management.schemas.student_attendance import (
    StudentAttendanceCreate,
    StudentAttendanceResponse,
    StudentAttendanceUpdate,
)
from database.session import get_db
from routes.service.crud.student_attendance import create_attendance, delete_attendance, update_attendance
from routes.service.student_attendance_kpi import build_student_attendance_kpi
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/student-attendance", tags=["Student Attendance"])


def _school_records(db: Session, school_id: UUID):
    # Attendance ownership is persisted on the record. Do not infer ownership
    # from a learner's current enrolment because learners can transfer schools.
    return db.query(StudentAttendance).filter(StudentAttendance.school_id == school_id)


def _school_record(db: Session, attendance_id: UUID, school_id: UUID):
    return _school_records(db, school_id).filter(StudentAttendance.id == attendance_id).first()


def _academic_period(db: Session, school_id: UUID, attendance_date):
    year = (
        db.query(AcademicYear)
        .filter(
            AcademicYear.school_id == school_id,
            AcademicYear.start_date <= attendance_date,
            AcademicYear.end_date >= attendance_date,
        )
        .first()
    )
    term = (
        db.query(AcademicTerm)
        .filter(
            AcademicTerm.school_id == school_id,
            AcademicTerm.start_date <= attendance_date,
            AcademicTerm.end_date >= attendance_date,
        )
        .first()
    )
    return year, term


@router.get("/kpi")
def attendance_dashboard_kpi(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return build_student_attendance_kpi(_school_records(db, context.school_id).all())


@router.post("/", response_model=StudentAttendanceResponse)
def create_student_attendance(
    payload: StudentAttendanceCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "vice_principal", "teacher", "class_teacher", "registrar")
    ),
):
    enrollment = (
        db.query(StudentEnrollment)
        .filter(
            StudentEnrollment.student_id == payload.student_id,
            StudentEnrollment.school_id == context.school_id,
            StudentEnrollment.is_current.is_(True),
        )
        .first()
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Student is not enrolled in this school")
    if payload.classroom_id is not None and enrollment.class_id != payload.classroom_id:
        raise HTTPException(status_code=400, detail="Student is not enrolled in the selected class")

    existing = (
        db.query(StudentAttendance)
        .filter(
            StudentAttendance.school_id == context.school_id,
            StudentAttendance.student_id == payload.student_id,
            StudentAttendance.attendance_date == payload.attendance_date,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Attendance is already recorded for this student on this date")

    attendance = create_attendance(db, payload)
    year, term = _academic_period(db, context.school_id, payload.attendance_date)
    attendance.school_id = context.school_id
    attendance.academic_year_id = year.id if year else None
    attendance.term_id = term.id if term else None
    if attendance.classroom_id is None:
        attendance.classroom_id = enrollment.class_id
    db.commit()
    db.refresh(attendance)
    return attendance


@router.get("/", response_model=list[StudentAttendanceResponse])
def get_all_student_attendance(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return _school_records(db, context.school_id).order_by(StudentAttendance.attendance_date.desc()).all()


@router.get("/{attendance_id}", response_model=StudentAttendanceResponse)
def get_single_student_attendance(
    attendance_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    attendance = _school_record(db, attendance_id, context.school_id)
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found in this school")
    return attendance


@router.put("/{attendance_id}", response_model=StudentAttendanceResponse)
def update_student_attendance(
    attendance_id: UUID,
    payload: StudentAttendanceUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "vice_principal", "teacher", "class_teacher", "registrar")
    ),
):
    attendance = _school_record(db, attendance_id, context.school_id)
    if attendance is None:
        raise HTTPException(status_code=404, detail="Attendance record not found in this school")

    if payload.classroom_id is not None:
        enrollment = (
            db.query(StudentEnrollment)
            .filter(
                StudentEnrollment.student_id == attendance.student_id,
                StudentEnrollment.school_id == context.school_id,
                StudentEnrollment.class_id == payload.classroom_id,
                StudentEnrollment.is_current.is_(True),
            )
            .first()
        )
        if enrollment is None:
            raise HTTPException(status_code=400, detail="Student is not enrolled in the selected class")

    attendance = update_attendance(db, attendance_id, payload)
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    attendance.school_id = context.school_id
    if payload.attendance_date is not None:
        year, term = _academic_period(db, context.school_id, payload.attendance_date)
        attendance.academic_year_id = year.id if year else None
        attendance.term_id = term.id if term else None
        db.commit()
        db.refresh(attendance)
    return attendance


@router.delete("/{attendance_id}")
def delete_student_attendance_route(
    attendance_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "vice_principal", "registrar")
    ),
):
    if _school_record(db, attendance_id, context.school_id) is None:
        raise HTTPException(status_code=404, detail="Attendance record not found in this school")
    attendance = delete_attendance(db, attendance_id)
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    return {"message": "Attendance deleted successfully"}
