from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_school_context_requires_membership_for_selected_workspace():
    code = source("utils/school_context.py")
    assert "SchoolMembership.user_id == user.id" in code
    assert "SchoolMembership.school_id == selected" in code
    assert "you do not belong to this school workspace" in code


def test_students_and_teachers_are_active_school_scoped():
    students = source("routes/students.py")
    teachers = source("routes/teacher.py")
    assert "StudentEnrollment.school_id == context.school_id" in students
    assert "Teacher.school_id == context.school_id" in teachers


def test_classes_use_school_mapping_not_global_deletion():
    classes = source("routes/class_route.py")
    assert ".join(SchoolClass" in classes
    assert "SchoolClass.school_id == context.school_id" in classes
    assert "db.delete(mapping)" in classes
    assert "db.delete(classroom)" not in classes


def test_shared_grade_catalog_is_platform_admin_managed():
    grades = source("routes/grade.py")
    assert "_require_platform_admin(context)" in grades
    assert "grade definitions are managed by the !thute Tutor platform" in grades


def test_employment_and_payroll_have_school_ownership():
    employee_model = source("database/employee_management/model/employee.py")
    payroll_route = source("routes/finance_management/employee_managemen/employee_management.py")
    assert "school_id = Column(" in employee_model
    assert "Employee.school_id == context.school_id" in payroll_route
    assert ".join(Employee" in payroll_route


def test_fee_payment_keeps_origin_school_after_student_transfer():
    payment_model = source("database/finace_management/models/studentFeePayment.py")
    payment_route = source("routes/finance_management/feePayment.py")
    assert "school_id = Column(" in payment_model
    assert "FeePayment.school_id == school_id" in payment_route
    assert "payment.school_id = school_id" in payment_route


def test_social_feed_uses_active_workspace_not_legacy_user_school():
    feed = source("routes/social/feed.py")
    assert "context: SchoolContext = Depends(get_school_context)" in feed
    assert "FeedPost.school_id == context.school_id" in feed
    assert "current_user.school_id" not in feed


def test_school_admin_legacy_urls_cannot_escape_active_workspace():
    admin = source("routes/finance_management/employee_managemen/school_admin.py")
    assert "if school_id != context.school_id" in admin
    assert "FeePayment.school_id == school_id" in admin
    assert "Employee.school_id == school_id" in admin
