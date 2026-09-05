from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT.parent / "sms-frontend"


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def frontend(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_completion_schema_is_alembic_owned_and_dependency_aware():
    migration = source("alembic/versions/tutor20260905_tutor_completion_schema.py")
    main = source("main.py")
    entrypoint = source("docker-entrypoint.sh")
    assert 'revision: str = "tutor20260905"' in migration
    for revision in ("96a1ccca8772", "57b15f2778a2", "9d592aa35f8f", "688417c77c3d", "87e989281ef3"):
        assert revision in migration
    assert "checkfirst=True" in migration
    assert "alembic upgrade heads" in entrypoint
    assert "ensure_tutor_extension_schema" not in main


def test_quiz_teacher_ownership_and_score_integrity_are_enforced():
    code = source("routes/quiz.py")
    assert "assessment.teacher_id != teacher_id" in code
    assert "assessment is not assigned to this teacher" in code
    assert "question points would exceed the assessment maximum score" in code
    assert "online assessment is not fully configured for its maximum score" in code
    assert "quiz response has already been marked" in code
    assert "sum((Decimal(str(row.awarded_points or 0)) for row in rows), Decimal(\"0\"))" in code


def test_quiz_drafts_are_staff_visible_but_not_learner_visible():
    code = source("routes/quiz.py")
    assert "if context.role == \"student\":" in code
    assert "if not assessment.is_published or not _student_can_take" in code
    assert "elif context.is_platform_admin or context.role in ASSESSMENT_STAFF" in code
    assert "questions cannot change after learner attempts have started" in code


def test_confidential_learner_records_require_school_relationships():
    admissions = source("routes/admissions.py")
    support = source("routes/student_support.py")
    for code in (admissions, support):
        assert "StudentEnrollment.school_id == school_id" in code
        assert "StudentEnrollment.student_id == student_id" in code
    assert "ParentStudent.parent_id == context.user_id" in admissions
    assert "not permitted to view this learner's documents" in admissions
    assert "ParentStudent.parent_id == context.user_id" in support
    assert "not permitted to view this learner's discipline record" in support
    assert "HEALTH_STAFF" in support


def test_learning_and_quiz_frontends_are_real_workspaces():
    learning = frontend("app/(dashboard)/dashboard/learning/page.tsx")
    quiz = frontend("app/(dashboard)/dashboard/quiz/page.tsx")
    navigation = frontend("components/sidebar_data.tsx")
    assert "submitAssignment" in learning
    assert "gradeSubmission" in learning
    assert "submitQuizAttempt" in quiz
    assert "markQuizResponse" in quiz
    assert 'url: "/dashboard/quiz"' in navigation
    assert 'url: "/dashboard/student-care"' in navigation
    assert 'url: "/dashboard/reports"' in navigation


def test_report_exports_have_pdf_and_xlsx_contracts():
    exports = source("routes/report_exports.py")
    api = frontend("api/reports/index.ts")
    assert '@router.get("/management.pdf")' in exports
    assert '@router.get("/management.xlsx")' in exports
    assert '"/api/reports/export/management.pdf"' in api
    assert '"/api/reports/export/management.xlsx"' in api


def test_tutor_push_integration_uses_central_push_service():
    notifications = source("utils/tutor_notifications.py")
    push = source("utils/ithute_push.py")
    assert "publish_notification" in notifications
    assert "recipient_sub" in push
    assert "PUSH_BASE_URL" in push
    assert "firebase" not in push.lower()
    assert "fcm" not in push.lower()
