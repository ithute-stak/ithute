from sqlalchemy import Column, String, ForeignKey, UUID, UniqueConstraint
from sqlalchemy.orm import relationship
from database.base import Base


class Class(Base):
    __tablename__ = "classes"

    name = Column(String(50), nullable=False)
    # Example: A, B, C

    grade_id = Column(
        UUID(as_uuid=True),
        ForeignKey("grades.id"),
        nullable=False
    )

    grade = relationship(
        "Grade",
        back_populates="classes"
    )

    students = relationship(
        "Student",
        back_populates="classroom"
    )

    attendance_records = relationship(
        "StudentAttendance",
        back_populates="classroom",
        cascade="all, delete"
    )

    # link to SchoolClass
    school_classes = relationship(
        "SchoolClass",
        back_populates="class_"
    )

    __table_args__ = (
        UniqueConstraint("grade_id", "name", name="uix_school_grade"),
    )