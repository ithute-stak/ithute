from sqlalchemy import Boolean, Column, Date, ForeignKey, String, UUID
from sqlalchemy.orm import relationship

from database.base import Base


class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"

    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="SET NULL"), nullable=True, index=True)
    term_id = Column(UUID(as_uuid=True), ForeignKey("academic_terms.id", ondelete="SET NULL"), nullable=True, index=True)

    # Legacy text fields remain for backward compatibility with existing data/UI.
    academic_year = Column(String(255))
    term = Column(String(255))

    start_date = Column(Date)
    end_date = Column(Date, nullable=True)
    status = Column(String(32), nullable=False, default="active")  # active|withdrawn|transferred|graduated|completed
    withdrawal_reason = Column(String(500), nullable=True)
    transfer_destination = Column(String(255), nullable=True)
    is_current = Column(Boolean, default=True, nullable=False)

    student = relationship("Student", back_populates="enrollments")
    classroom = relationship("Class")
