"""Tutor academic, learning and operations completion schema.

Revision ID: tutor20260905
Revises: independent Tutor branch
Create Date: 2026-09-05

The imported Tutor database has a deliberate multi-head Alembic history. This
revision is a dependency-aware branch and the container entrypoint upgrades
`heads`, not a single head. `checkfirst=True` also makes the revision safe for
environments where an earlier compatibility bootstrap already provisioned the
new tables before this revision was introduced.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

from database.base import Base
from database.multi_tenant_school_management.models import academic_core as _academic_core  # noqa: F401
from database.multi_tenant_school_management.models import administration as _administration  # noqa: F401
from database.multi_tenant_school_management.models import tutor_assessment as _assessment  # noqa: F401
from database.multi_tenant_school_management.models import tutor_completion as _completion  # noqa: F401


revision: str = "tutor20260905"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("tutor_completion",)
depends_on: Union[str, Sequence[str], None] = (
    "96a1ccca8772",  # schools/users/classes/students/teachers/enrolments
    "57b15f2778a2",  # grades
    "9d592aa35f8f",  # subjects
    "688417c77c3d",  # student attendance
    "87e989281ef3",  # employees
)


TABLE_NAMES = (
    "academic_years",
    "academic_terms",
    "teaching_assignments",
    "timetable_entries",
    "assessments",
    "assessment_results",
    "admission_applications",
    "student_documents",
    "lessons",
    "assignments",
    "assignment_submissions",
    "question_bank_items",
    "mastery_records",
    "study_plans",
    "discipline_incidents",
    "student_health_records",
    "school_calendar_events",
    "library_books",
    "library_loans",
    "transport_routes",
    "transport_assignments",
    "inventory_assets",
    "quiz_attempts",
    "quiz_responses",
    "staff_leave_requests",
    "suppliers",
    "purchase_orders",
    "school_expenses",
)


def _tables():
    missing = [name for name in TABLE_NAMES if name not in Base.metadata.tables]
    if missing:
        raise RuntimeError(f"Tutor migration metadata missing tables: {', '.join(missing)}")
    return [Base.metadata.tables[name] for name in TABLE_NAMES]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=_tables(), checkfirst=True)

    # School-owned longitudinal enrolment and attendance columns are additive
    # compatibility changes. The existing post-Alembic compatibility script
    # performs conservative data backfill without guessing cross-school history.
    op.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS academic_year_id UUID REFERENCES academic_years(id) ON DELETE SET NULL"))
    op.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES academic_terms(id) ON DELETE SET NULL"))
    op.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active'"))
    op.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS withdrawal_reason VARCHAR(500)"))
    op.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS transfer_destination VARCHAR(255)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_student_enrollments_academic_year_id ON student_enrollments (academic_year_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_student_enrollments_term_id ON student_enrollments (term_id)"))

    op.execute(text("ALTER TABLE student_attendance ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id) ON DELETE CASCADE"))
    op.execute(text("ALTER TABLE student_attendance ADD COLUMN IF NOT EXISTS academic_year_id UUID REFERENCES academic_years(id) ON DELETE SET NULL"))
    op.execute(text("ALTER TABLE student_attendance ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES academic_terms(id) ON DELETE SET NULL"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_student_attendance_school_id ON student_attendance (school_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_student_attendance_academic_year_id ON student_attendance (academic_year_id)"))
    op.execute(text("CREATE INDEX IF NOT EXISTS ix_student_attendance_term_id ON student_attendance (term_id)"))


def downgrade() -> None:
    bind = op.get_bind()

    # Remove compatibility FKs before academic_years/academic_terms are dropped.
    op.execute(text("DROP INDEX IF EXISTS ix_student_attendance_term_id"))
    op.execute(text("DROP INDEX IF EXISTS ix_student_attendance_academic_year_id"))
    op.execute(text("DROP INDEX IF EXISTS ix_student_attendance_school_id"))
    op.execute(text("ALTER TABLE student_attendance DROP COLUMN IF EXISTS term_id"))
    op.execute(text("ALTER TABLE student_attendance DROP COLUMN IF EXISTS academic_year_id"))
    op.execute(text("ALTER TABLE student_attendance DROP COLUMN IF EXISTS school_id"))

    op.execute(text("DROP INDEX IF EXISTS ix_student_enrollments_term_id"))
    op.execute(text("DROP INDEX IF EXISTS ix_student_enrollments_academic_year_id"))
    op.execute(text("ALTER TABLE student_enrollments DROP COLUMN IF EXISTS transfer_destination"))
    op.execute(text("ALTER TABLE student_enrollments DROP COLUMN IF EXISTS withdrawal_reason"))
    op.execute(text("ALTER TABLE student_enrollments DROP COLUMN IF EXISTS status"))
    op.execute(text("ALTER TABLE student_enrollments DROP COLUMN IF EXISTS term_id"))
    op.execute(text("ALTER TABLE student_enrollments DROP COLUMN IF EXISTS academic_year_id"))

    # SQLAlchemy sorts the remaining extension tables by FK dependency.
    Base.metadata.drop_all(bind=bind, tables=_tables(), checkfirst=True)
