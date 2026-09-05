from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from database.base import Base


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="in_progress", index=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    score = Column(Numeric(10, 2), nullable=True)
    max_score = Column(Numeric(10, 2), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('in_progress','submitted','needs_review','graded')", name="ck_quiz_attempt_status"),
    )


class QuizResponse(Base):
    __tablename__ = "quiz_responses"

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("question_bank_items.id", ondelete="CASCADE"), nullable=False, index=True)
    answer = Column(JSON, nullable=True)
    is_correct = Column(String(12), nullable=True)
    awarded_points = Column(Numeric(10, 2), nullable=True)

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_quiz_response_attempt_question"),
        CheckConstraint("awarded_points IS NULL OR awarded_points >= 0", name="ck_quiz_response_points"),
    )
