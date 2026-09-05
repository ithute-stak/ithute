import uuid

from sqlalchemy import text

from database.session import engine


SCHEMA_STATEMENTS = (
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_user_id UUID",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_auth_user_id ON users (auth_user_id) WHERE auth_user_id IS NOT NULL",
    "ALTER TABLE users ALTER COLUMN password DROP NOT NULL",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS slug VARCHAR(120)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS logo_url VARCHAR(1000)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS motto VARCHAR(500)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS primary_color VARCHAR(32)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS secondary_color VARCHAR(32)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS accent_color VARCHAR(32)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS address TEXT",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS phone VARCHAR(80)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS website VARCHAR(500)",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS timezone VARCHAR(80) NOT NULL DEFAULT 'Africa/Maseru'",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'LSL'",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS locale VARCHAR(20) NOT NULL DEFAULT 'en-LS'",
    "ALTER TABLE schools ADD COLUMN IF NOT EXISTS settings_json JSONB NOT NULL DEFAULT '{}'::jsonb",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_schools_slug ON schools (slug) WHERE slug IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_schools_is_active ON schools (is_active)",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id) ON DELETE CASCADE",
    "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE",
    "CREATE INDEX IF NOT EXISTS ix_notifications_school_id ON notifications (school_id)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_notifications_channel ON notifications (channel)",
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id) ON DELETE CASCADE",
    "CREATE INDEX IF NOT EXISTS ix_employees_school_id ON employees (school_id)",
    "ALTER TABLE fee_payments ADD COLUMN IF NOT EXISTS school_id UUID REFERENCES schools(id) ON DELETE RESTRICT",
    "CREATE INDEX IF NOT EXISTS ix_fee_payments_school_id ON fee_payments (school_id)",
    """
    CREATE TABLE IF NOT EXISTS school_memberships (
        id UUID PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        created_by VARCHAR(36),
        updated_by VARCHAR(36),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        school_id UUID NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
        role VARCHAR(64) NOT NULL,
        title VARCHAR(120),
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        is_default BOOLEAN NOT NULL DEFAULT FALSE,
        CONSTRAINT uq_school_membership_user_school UNIQUE (user_id, school_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_school_memberships_user_id ON school_memberships (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_school_memberships_school_id ON school_memberships (school_id)",
    "CREATE INDEX IF NOT EXISTS ix_school_memberships_role ON school_memberships (role)",
    "CREATE INDEX IF NOT EXISTS ix_school_memberships_is_active ON school_memberships (is_active)",
)


EMPLOYEE_BACKFILLS = (
    ("teachers", "UPDATE employees e SET school_id = t.school_id FROM teachers t WHERE t.employee_id = e.id AND e.school_id IS NULL"),
    ("school_admins", "UPDATE employees e SET school_id = a.school_id FROM school_admins a WHERE a.employee_id = e.id AND e.school_id IS NULL"),
    ("principals", "UPDATE employees e SET school_id = p.school_id FROM principals p WHERE p.employee_id = e.id AND e.school_id IS NULL"),
    ("vice_principals", "UPDATE employees e SET school_id = v.school_id FROM vice_principals v WHERE v.employee_id = e.id AND e.school_id IS NULL"),
)


if __name__ == "__main__":
    with engine.begin() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(text(statement))

        rows = connection.execute(
            text("SELECT id, school_id, role::text AS role FROM users WHERE school_id IS NOT NULL")
        ).mappings()
        for row in rows:
            connection.execute(
                text(
                    """
                    INSERT INTO school_memberships
                        (id, user_id, school_id, role, title, is_active, is_default)
                    VALUES
                        (:id, :user_id, :school_id, :role, :title, TRUE, TRUE)
                    ON CONFLICT (user_id, school_id) DO NOTHING
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "user_id": row["id"],
                    "school_id": row["school_id"],
                    "role": row["role"],
                    "title": "Migrated school membership",
                },
            )

        for table_name, statement in EMPLOYEE_BACKFILLS:
            exists = connection.execute(
                text("SELECT to_regclass(:table_name) IS NOT NULL"),
                {"table_name": table_name},
            ).scalar()
            if exists:
                connection.execute(text(statement))

        enrollment_table_exists = connection.execute(
            text("SELECT to_regclass('student_enrollments') IS NOT NULL")
        ).scalar()
        if enrollment_table_exists:
            connection.execute(
                text(
                    """
                    WITH unambiguous AS (
                        SELECT student_id, (array_agg(DISTINCT school_id))[1] AS school_id
                        FROM student_enrollments
                        WHERE school_id IS NOT NULL
                        GROUP BY student_id
                        HAVING COUNT(DISTINCT school_id) = 1
                    )
                    UPDATE fee_payments p
                    SET school_id = u.school_id
                    FROM unambiguous u
                    WHERE p.student_id = u.student_id
                      AND p.school_id IS NULL
                    """
                )
            )

    print("Tutor central-auth and school-workspace schema is ready.")
