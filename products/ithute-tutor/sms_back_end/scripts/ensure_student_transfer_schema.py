from sqlalchemy import text

from database.base import Base
# Import the model package first so all FK target tables (schools, users,
# classes, students) are registered in SQLAlchemy metadata before create_all.
from database.multi_tenant_school_management import models as _school_models  # noqa: F401
from database.multi_tenant_school_management.models.student_transfer import StudentTransfer, StudentTransferEvent
from database.session import engine


if __name__ == "__main__":
    # create_all handles fresh installations. The ALTER statements below make
    # this safe for existing Tutor databases that already have student_transfers.
    Base.metadata.create_all(
        bind=engine,
        tables=[StudentTransfer.__table__, StudentTransferEvent.__table__],
        checkfirst=True,
    )

    statements = [
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS reference_number VARCHAR(40)",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS transfer_reason VARCHAR(80)",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS destination_note VARCHAR(1000)",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR(1000)",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS consent_confirmed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS records_verified BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS proposed_start_date DATE",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS destination_class_id UUID REFERENCES classes(id) ON DELETE SET NULL",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS released_at TIMESTAMP",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS released_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS claimed_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS accepted_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS rejected_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE student_transfers ADD COLUMN IF NOT EXISTS cancelled_by UUID REFERENCES users(id) ON DELETE SET NULL",
        "UPDATE student_transfers SET status = 'released' WHERE status = 'pending'",
        "UPDATE student_transfers SET released_at = COALESCE(released_at, created_at) WHERE released_at IS NULL",
        "UPDATE student_transfers SET reference_number = 'TR-' || TO_CHAR(COALESCE(released_at, created_at), 'YYYY') || '-' || UPPER(SUBSTRING(REPLACE(id::text, '-', '') FROM 1 FOR 10)) WHERE reference_number IS NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_student_transfers_reference_number ON student_transfers(reference_number)",
        "CREATE INDEX IF NOT EXISTS ix_student_transfer_events_transfer_id ON student_transfer_events(transfer_id)",
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    print("Tutor professional learner-transfer schema is ready.")
