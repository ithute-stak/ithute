from sqlalchemy import Column, Date, ForeignKey, String, UniqueConstraint, UUID
from sqlalchemy.orm import relationship

from database.base import Base


class StudentAttendance(Base):
    __tablename__ = "student_attendance"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    academic_year_id = Column(
        UUID(as_uuid=True),
        ForeignKey("academic_years.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    term_id = Column(
        UUID(as_uuid=True),
        ForeignKey("academic_terms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.id"),
        nullable=False,
    )

    classroom_id = Column(
        UUID(as_uuid=True),
        ForeignKey("classes.id"),
        nullable=True,
    )

    attendance_date = Column(Date, nullable=False)

    # present | absent | late | excused
    status = Column(String, nullable=False, default="present")
    remarks = Column(String, nullable=True)

    student = relationship("Student", back_populates="attendance_records")
    classroom = relationship("Class", back_populates="attendance_records")

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "student_id",
            "attendance_date",
            name="uq_student_attendance_school_day",
        ),
    )
