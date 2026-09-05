from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    UUID,
)
from sqlalchemy.orm import relationship

from database.base import Base


class AcademicYear(Base):
    __tablename__ = "academic_years"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_current = Column(Boolean, nullable=False, default=False)
    is_closed = Column(Boolean, nullable=False, default=False)

    terms = relationship("AcademicTerm", back_populates="academic_year", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_academic_year_school_name"),
        CheckConstraint("end_date >= start_date", name="ck_academic_year_dates"),
    )


class AcademicTerm(Base):
    __tablename__ = "academic_terms"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    sequence = Column(Integer, nullable=False, default=1)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_current = Column(Boolean, nullable=False, default=False)
    is_closed = Column(Boolean, nullable=False, default=False)

    academic_year = relationship("AcademicYear", back_populates="terms")

    __table_args__ = (
        UniqueConstraint("academic_year_id", "name", name="uq_academic_term_year_name"),
        UniqueConstraint("academic_year_id", "sequence", name="uq_academic_term_year_sequence"),
        CheckConstraint("end_date >= start_date", name="ck_academic_term_dates"),
        CheckConstraint("sequence > 0", name="ck_academic_term_sequence"),
    )


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False, index=True)
    term_id = Column(UUID(as_uuid=True), ForeignKey("academic_terms.id", ondelete="CASCADE"), nullable=True, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    is_class_teacher = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)

    teacher = relationship("Teacher")
    classroom = relationship("Class")
    subject = relationship("Subject")
    academic_year = relationship("AcademicYear")
    term = relationship("AcademicTerm")

    __table_args__ = (
        UniqueConstraint(
            "school_id", "academic_year_id", "term_id", "teacher_id", "class_id", "subject_id",
            name="uq_teaching_assignment_scope",
        ),
    )


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False, index=True)
    term_id = Column(UUID(as_uuid=True), ForeignKey("academic_terms.id", ondelete="CASCADE"), nullable=False, index=True)
    teaching_assignment_id = Column(UUID(as_uuid=True), ForeignKey("teaching_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    room = Column(String(120), nullable=True)
    notes = Column(String(500), nullable=True)

    teaching_assignment = relationship("TeachingAssignment")

    __table_args__ = (
        UniqueConstraint(
            "school_id", "term_id", "teaching_assignment_id", "day_of_week", "start_time",
            name="uq_timetable_assignment_slot",
        ),
        CheckConstraint("day_of_week >= 1 AND day_of_week <= 7", name="ck_timetable_day"),
        CheckConstraint("end_time > start_time", name="ck_timetable_time"),
    )


class Assessment(Base):
    __tablename__ = "assessments"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False, index=True)
    term_id = Column(UUID(as_uuid=True), ForeignKey("academic_terms.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(160), nullable=False)
    assessment_type = Column(String(40), nullable=False, default="test")
    description = Column(Text, nullable=True)
    assessment_date = Column(Date, nullable=False)
    max_score = Column(Numeric(10, 2), nullable=False)
    weight = Column(Numeric(7, 4), nullable=False, default=1)
    is_published = Column(Boolean, nullable=False, default=False)
    is_locked = Column(Boolean, nullable=False, default=False)

    classroom = relationship("Class")
    subject = relationship("Subject")
    teacher = relationship("Teacher")
    results = relationship("AssessmentResult", back_populates="assessment", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("max_score > 0", name="ck_assessment_max_score"),
        CheckConstraint("weight > 0", name="ck_assessment_weight"),
    )


class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    score = Column(Numeric(10, 2), nullable=True)
    is_absent = Column(Boolean, nullable=False, default=False)
    is_excused = Column(Boolean, nullable=False, default=False)
    remarks = Column(String(500), nullable=True)

    assessment = relationship("Assessment", back_populates="results")
    student = relationship("Student")

    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", name="uq_assessment_result_student"),
        CheckConstraint("score IS NULL OR score >= 0", name="ck_assessment_result_score"),
    )
