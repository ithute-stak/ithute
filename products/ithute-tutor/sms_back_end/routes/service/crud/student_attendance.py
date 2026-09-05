# services/student_attendance.py

from uuid import UUID

from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import StudentAttendance
from database.multi_tenant_school_management.schemas.student_attendance import StudentAttendanceCreate, StudentAttendanceUpdate


# =========================
# CREATE
# =========================

def create_attendance(
    db: Session,
    payload: StudentAttendanceCreate
):

    attendance = StudentAttendance(
        **payload.model_dump()
    )

    db.add(attendance)

    db.commit()

    db.refresh(attendance)

    return attendance


# =========================
# GET ALL
# =========================

def get_attendance_records(
    db: Session
):

    return (
        db.query(StudentAttendance)
        .all()
    )


# =========================
# GET ONE
# =========================

def get_attendance_record(
    db: Session,
    attendance_id: UUID
):

    return (
        db.query(StudentAttendance)
        .filter(
            StudentAttendance.id == attendance_id
        )
        .first()
    )


# =========================
# UPDATE
# =========================

def update_attendance(
    db: Session,
    attendance_id: UUID,
    payload: StudentAttendanceUpdate
):

    attendance = get_attendance_record(
        db,
        attendance_id
    )

    if not attendance:
        return None

    update_data = payload.model_dump(
        exclude_unset=True
    )

    for key, value in update_data.items():

        setattr(
            attendance,
            key,
            value
        )

    db.commit()

    db.refresh(attendance)

    return attendance


# =========================
# DELETE
# =========================

def delete_attendance(
    db: Session,
    attendance_id: UUID
):

    attendance = get_attendance_record(
        db,
        attendance_id
    )

    if not attendance:
        return None

    db.delete(attendance)

    db.commit()

    return attendance