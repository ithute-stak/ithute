"""Provision Tutor's school-owned academic core safely.

Tutor inherited a multi-head Alembic history. The normal entrypoint upgrades all
heads first; this idempotent compatibility step creates the new academic tables
and upgrades legacy attendance/enrolment without dropping existing data.
"""

import uuid

from sqlalchemy import text

from database.base import Base
from database.session import engine
from database.multi_tenant_school_management.models.academic_core import (
    AcademicTerm,
    AcademicYear,
    Assessment,
    AssessmentResult,
    TeachingAssignment,
    TimetableEntry,
)


ACADEMIC_TABLES = [
    AcademicYear.__table__,
    AcademicTerm.__table__,
    TeachingAssignment.__table__,
    TimetableEntry.__table__,
    Assessment.__table__,
    AssessmentResult.__table__,
]


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine, tables=ACADEMIC_TABLES, checkfirst=True)

    with engine.begin() as connection:
        # Student enrolment is the immutable school-history bridge for one
        # global learner identity.
        connection.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS academic_year_id UUID REFERENCES academic_years(id) ON DELETE SET NULL"))
        connection.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES academic_terms(id) ON DELETE SET NULL"))
        connection.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active'"))
        connection.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS withdrawal_reason VARCHAR(500)"))
        connection.execute(text("ALTER TABLE student_enrollments ADD COLUMN IF NOT EXISTS transfer_destination VARCHAR(255)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_student_enrollments_academic_year_id ON student_enrollments (academic_year_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_student_enrollments_term_id ON student_enrollments (term_id)"))
        connection.execute(text("UPDATE student_enrollments SET status = CASE WHEN is_current THEN 'active' ELSE COALESCE(NULLIF(status, 'active'), 'completed') END WHERE status IS NULL OR (NOT is_current AND status = 'active')"))

        # Older Tutor data sometimes attached a student only through users.school_id.
        # Convert that already-existing relationship once into the explicit
        # enrollment table before runtime code stops relying on the legacy field.
        legacy_students = connection.execute(text("""
            SELECT s.id AS student_id, u.school_id, s.class_id
            FROM students s
            JOIN users u ON u.id = s.id
            WHERE u.school_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM student_enrollments e
                  WHERE e.student_id = s.id AND e.school_id = u.school_id
              )
        """)).mappings().all()
        for row in legacy_students:
            connection.execute(
                text("""
                    INSERT INTO student_enrollments
                        (id, student_id, class_id, school_id, start_date, status, is_current)
                    VALUES
                        (:id, :student_id, :class_id, :school_id, CURRENT_DATE, 'active', TRUE)
                """),
                {
                    "id": uuid.uuid4(),
                    "student_id": row["student_id"],
                    "class_id": row["class_id"],
                    "school_id": row["school_id"],
                },
            )

        # Map legacy text/date enrolments into the new school academic periods
        # where there is a deterministic date match.
        connection.execute(text("""
            UPDATE student_enrollments e
            SET academic_year_id = y.id
            FROM academic_years y
            WHERE e.school_id = y.school_id
              AND e.start_date BETWEEN y.start_date AND y.end_date
              AND e.academic_year_id IS NULL
        """))
        connection.execute(text("""
            UPDATE student_enrollments e
            SET term_id = t.id
            FROM academic_terms t
            WHERE e.school_id = t.school_id
              AND e.start_date BETWEEN t.start_date AND t.end_date
              AND e.term_id IS NULL
        """))

        # Attendance records own their school permanently; never determine an
        # old record by whichever school the learner belongs to today.
        connection.execute(text("ALTER TABLE student_attendance ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id) ON DELETE CASCADE"))
        connection.execute(text("ALTER TABLE student_attendance ADD COLUMN IF NOT EXISTS academic_year_id UUID REFERENCES academic_years(id) ON DELETE SET NULL"))
        connection.execute(text("ALTER TABLE student_attendance ADD COLUMN IF NOT EXISTS term_id UUID REFERENCES academic_terms(id) ON DELETE SET NULL"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_student_attendance_school_id ON student_attendance (school_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_student_attendance_academic_year_id ON student_attendance (academic_year_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_student_attendance_term_id ON student_attendance (term_id)"))

        # Preserve history only where school ownership is certain. If a learner
        # has attended multiple schools, legacy attendance is left unassigned for
        # audited reconciliation rather than guessed from the current school.
        connection.execute(text("""
            WITH unambiguous AS (
                SELECT student_id, (array_agg(DISTINCT school_id))[1] AS school_id
                FROM student_enrollments
                WHERE school_id IS NOT NULL
                GROUP BY student_id
                HAVING COUNT(DISTINCT school_id) = 1
            )
            UPDATE student_attendance a
            SET school_id = u.school_id
            FROM unambiguous u
            WHERE a.student_id = u.student_id
              AND a.school_id IS NULL
        """))

        connection.execute(text("""
            UPDATE student_attendance a
            SET academic_year_id = y.id
            FROM academic_years y
            WHERE a.school_id = y.school_id
              AND a.attendance_date BETWEEN y.start_date AND y.end_date
              AND a.academic_year_id IS NULL
        """))
        connection.execute(text("""
            UPDATE student_attendance a
            SET term_id = t.id
            FROM academic_terms t
            WHERE a.school_id = t.school_id
              AND a.attendance_date BETWEEN t.start_date AND t.end_date
              AND a.term_id IS NULL
        """))

    print("Tutor academic-core, enrolment and attendance schema is ready.")
