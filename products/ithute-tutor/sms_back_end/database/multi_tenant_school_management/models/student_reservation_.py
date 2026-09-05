import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID

from database.base import Base


class StudentAdmissionReservation(Base):
    __tablename__ = "student_admission_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    admission_number = Column(String(255), unique=True, nullable=False)

    is_used = Column(Boolean, default=False, nullable=False)

    expires_at = Column(DateTime(timezone=True), nullable=False)