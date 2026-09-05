import logging

from database.base import Base
from database.session import engine

# Importing these modules registers their tables with the shared SQLAlchemy metadata.
from database.multi_tenant_school_management.models import academic_core as _academic_core  # noqa: F401
from database.multi_tenant_school_management.models import tutor_completion as _completion  # noqa: F401
from database.multi_tenant_school_management.models import tutor_assessment as _assessment  # noqa: F401
from database.multi_tenant_school_management.models import administration as _administration  # noqa: F401

logger = logging.getLogger("ithute_tutor.schema")

TUTOR_EXTENSION_TABLES = (
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


def ensure_tutor_extension_schema() -> None:
    """Create only new Tutor extension tables when they are absent.

    The imported legacy application has an old, divergent Alembic history. This
    bootstrap is deliberately limited to brand-new tables and never alters or
    drops an existing table/column. Existing schema evolution remains under
    Alembic; this keeps fresh and upgraded Tutor installations runnable while
    the legacy migration graph is consolidated.
    """
    tables = [Base.metadata.tables[name] for name in TUTOR_EXTENSION_TABLES if name in Base.metadata.tables]
    missing_metadata = sorted(set(TUTOR_EXTENSION_TABLES) - {table.name for table in tables})
    if missing_metadata:
        raise RuntimeError(f"Tutor extension metadata missing: {', '.join(missing_metadata)}")
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    logger.info("Tutor extension schema verified tables=%s", len(tables))
