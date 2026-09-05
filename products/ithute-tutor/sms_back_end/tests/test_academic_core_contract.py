from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_academic_records_persist_school_ownership():
    code = source("database/multi_tenant_school_management/models/academic_core.py")
    for model in (
        "class AcademicYear",
        "class AcademicTerm",
        "class TeachingAssignment",
        "class TimetableEntry",
        "class Assessment",
        "class AssessmentResult",
    ):
        assert model in code
    assert code.count('ForeignKey("schools.id"') >= 6


def test_academic_routes_derive_school_from_server_context():
    code = source("routes/academic_core.py")
    assert "context.school_id" in code
    assert "SchoolClass.school_id == school_id" in code
    assert "SchoolGradeSubject.school_id == school_id" in code
    assert "Teacher.school_id == school_id" in code
    assert "StudentEnrollment.school_id == school_id" in code


def test_timetable_blocks_teacher_and_class_collisions():
    code = source("routes/academic_core.py")
    assert "TimetableEntry.start_time < payload.end_time" in code
    assert "TimetableEntry.end_time > payload.start_time" in code
    assert "TeachingAssignment.teacher_id == assignment.teacher_id" in code
    assert "TeachingAssignment.class_id == assignment.class_id" in code


def test_marks_are_bounded_and_report_cards_only_use_published_assessments():
    code = source("routes/academic_core.py")
    assert "payload.score > assessment.max_score" in code
    assert "Assessment.is_published.is_(True)" in code
    assert '"overall_percentage"' in code


def test_attendance_is_owned_by_origin_school_not_current_enrollment():
    model = source("database/multi_tenant_school_management/models/student_attendance.py")
    route = source("routes/student_attendance.py")
    assert "school_id = Column(" in model
    assert "StudentAttendance.school_id == school_id" in route
    assert "Attendance ownership is persisted on the record" in route
    assert ".join(StudentEnrollment" not in route


def test_learner_transfer_closes_enrollment_instead_of_rewriting_identity():
    model = source("database/multi_tenant_school_management/models/student_enrollment.py")
    route = source("routes/students.py")
    assert "withdrawal_reason" in model
    assert "transfer_destination" in model
    assert 'status: str = Field(pattern="^(withdrawn|transferred|graduated|completed)$")' in route
    assert "enrollment.is_current = False" in route
    assert "db.delete(student)" in route  # platform-only deletion remains explicit
    assert "withdraw the school enrolment instead of deleting the learner" in route


def test_startup_provisions_academic_core_after_existing_migrations():
    entrypoint = source("docker-entrypoint.sh")
    schema = source("scripts/ensure_academic_core_schema.py")
    assert "alembic upgrade heads" in entrypoint
    assert "python scripts/ensure_academic_core_schema.py" in entrypoint
    assert "Base.metadata.create_all" in schema
    assert "HAVING COUNT(DISTINCT school_id) = 1" in schema
