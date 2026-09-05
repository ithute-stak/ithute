from sqlalchemy import Column, UUID, ForeignKey, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship

from database.base import Base


class SchoolGradeSubject(Base):
    __tablename__ = "school_grade_subjects"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)

    # 🔥 rules per grade
    daily_credit_hours = Column(Integer, nullable=False)
    weekly_credit_hours = Column(Integer, nullable=False)

    # optional future fields
    is_core = Column(Boolean, default=True)

    # relationships
    school = relationship("School", back_populates="grade_subjects")
    grade = relationship("Grade", back_populates="subjects")
    subject = relationship("Subject", back_populates="grade_links")

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "grade_id",
            "subject_id",
            name="uix_grade_subject"
        ),
    )