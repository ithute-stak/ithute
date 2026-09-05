# schemas/student_attendance.py

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# =========================
# BASE
# =========================

class StudentAttendanceBase(BaseModel):

    student_id: UUID

    classroom_id: Optional[UUID] = None

    attendance_date: date

    status: str = "present"

    remarks: Optional[str] = None


# =========================
# CREATE
# =========================

class StudentAttendanceCreate(
    StudentAttendanceBase
):
    pass


# =========================
# UPDATE
# =========================

class StudentAttendanceUpdate(BaseModel):

    classroom_id: Optional[UUID] = None

    attendance_date: Optional[date] = None

    status: Optional[str] = None

    remarks: Optional[str] = None


# =========================
# RESPONSE
# =========================

class StudentAttendanceResponse(
    StudentAttendanceBase
):

    id: UUID

    created_at: datetime

    updated_at: datetime

    model_config = {
        "from_attributes": True
    }