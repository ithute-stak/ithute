from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from database.base import Base


class AdmissionApplication(Base):
    __tablename__ = "admission_applications"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    applicant_first_name = Column(String(120), nullable=False)
    applicant_last_name = Column(String(120), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    guardian_name = Column(String(200), nullable=False)
    guardian_email = Column(String(255), nullable=True)
    guardian_phone = Column(String(80), nullable=True)
    desired_grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    desired_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(32), nullable=False, default="submitted", index=True)
    notes = Column(Text, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','submitted','under_review','accepted','waitlisted','rejected','enrolled')",
            name="ck_admission_application_status",
        ),
    )


class StudentDocument(Base):
    __tablename__ = "student_documents"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    document_type = Column(String(80), nullable=False)
    title = Column(String(200), nullable=False)
    storage_url = Column(Text, nullable=False)
    status = Column(String(24), nullable=False, default="pending")
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)


class Lesson(Base):
    __tablename__ = "lessons"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    resource_url = Column(Text, nullable=True)
    sequence = Column(Integer, nullable=False, default=1)
    status = Column(String(24), nullable=False, default="draft", index=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_lesson_sequence"),
        CheckConstraint("status IN ('draft','published','archived')", name="ck_lesson_status"),
    )


class Assignment(Base):
    __tablename__ = "assignments"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    instructions = Column(Text, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    max_score = Column(Numeric(10, 2), nullable=False, default=100)
    status = Column(String(24), nullable=False, default="draft", index=True)
    allow_resubmission = Column(Boolean, nullable=False, default=True)
    published_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("max_score > 0", name="ck_assignment_max_score"),
        CheckConstraint("status IN ('draft','published','closed','archived')", name="ck_assignment_status"),
    )


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no = Column(Integer, nullable=False, default=1)
    answer_text = Column(Text, nullable=True)
    attachment_url = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="submitted", index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    score = Column(Numeric(10, 2), nullable=True)
    feedback = Column(Text, nullable=True)
    graded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    graded_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", "attempt_no", name="uq_assignment_submission_attempt"),
        CheckConstraint("attempt_no > 0", name="ck_assignment_submission_attempt"),
        CheckConstraint("score IS NULL OR score >= 0", name="ck_assignment_submission_score"),
    )


class QuestionBankItem(Base):
    __tablename__ = "question_bank_items"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True, index=True)
    assessment_id = Column(UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True)
    topic_key = Column(String(160), nullable=True, index=True)
    prompt = Column(Text, nullable=False)
    question_type = Column(String(32), nullable=False, default="short_answer")
    choices = Column(JSON, nullable=True)
    correct_answer = Column(JSON, nullable=True)
    points = Column(Numeric(10, 2), nullable=False, default=1)
    explanation = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="active")


class MasteryRecord(Base):
    __tablename__ = "mastery_records"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_key = Column(String(160), nullable=False)
    mastery_score = Column(Numeric(5, 2), nullable=False, default=0)
    evidence_count = Column(Integer, nullable=False, default=0)
    last_evidence = Column(String(240), nullable=True)
    last_evidence_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("school_id", "student_id", "subject_id", "topic_key", name="uq_mastery_student_topic"),
        CheckConstraint("mastery_score >= 0 AND mastery_score <= 100", name="ck_mastery_score"),
        CheckConstraint("evidence_count >= 0", name="ck_mastery_evidence_count"),
    )


class StudyPlan(Base):
    __tablename__ = "study_plans"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    reason = Column(Text, nullable=True)
    items = Column(JSON, nullable=False, default=list)
    status = Column(String(24), nullable=False, default="active", index=True)


class DisciplineIncident(Base):
    __tablename__ = "discipline_incidents"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(80), nullable=False)
    severity = Column(String(24), nullable=False, default="low")
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    occurred_on = Column(Date, nullable=False)
    action_taken = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="open")


class StudentHealthRecord(Base):
    __tablename__ = "student_health_records"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    allergies = Column(Text, nullable=True)
    conditions = Column(Text, nullable=True)
    medications = Column(Text, nullable=True)
    emergency_notes = Column(Text, nullable=True)
    emergency_contact = Column(String(200), nullable=True)

    __table_args__ = (
        UniqueConstraint("school_id", "student_id", name="uq_health_record_school_student"),
    )


class SchoolCalendarEvent(Base):
    __tablename__ = "school_calendar_events"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(80), nullable=False, default="school")
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    audience = Column(String(80), nullable=False, default="all")


class LibraryBook(Base):
    __tablename__ = "library_books"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    isbn = Column(String(40), nullable=True)
    title = Column(String(240), nullable=False)
    author = Column(String(200), nullable=True)
    category = Column(String(100), nullable=True)
    copies_total = Column(Integer, nullable=False, default=1)
    copies_available = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        CheckConstraint("copies_total >= 0", name="ck_library_copies_total"),
        CheckConstraint("copies_available >= 0 AND copies_available <= copies_total", name="ck_library_copies_available"),
    )


class LibraryLoan(Base):
    __tablename__ = "library_loans"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("library_books.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    borrowed_at = Column(DateTime(timezone=True), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    returned_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(24), nullable=False, default="borrowed", index=True)
    fine_amount = Column(Numeric(12, 2), nullable=False, default=0)


class TransportRoute(Base):
    __tablename__ = "transport_routes"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    driver_name = Column(String(160), nullable=True)
    driver_phone = Column(String(80), nullable=True)
    vehicle_registration = Column(String(80), nullable=True)
    stops = Column(JSON, nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)


class TransportAssignment(Base):
    __tablename__ = "transport_assignments"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    route_id = Column(UUID(as_uuid=True), ForeignKey("transport_routes.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    pickup_stop = Column(String(200), nullable=True)
    dropoff_stop = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("route_id", "student_id", name="uq_transport_route_student"),
    )


class InventoryAsset(Base):
    __tablename__ = "inventory_assets"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_code = Column(String(80), nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    location = Column(String(160), nullable=True)
    status = Column(String(32), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("school_id", "asset_code", name="uq_inventory_asset_code"),
        CheckConstraint("quantity >= 0", name="ck_inventory_asset_quantity"),
    )
