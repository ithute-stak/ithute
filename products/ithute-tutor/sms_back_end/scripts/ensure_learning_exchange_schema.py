"""Provision the Tutor cross-school learning exchange tables.

Tutor currently carries multiple Alembic heads, so deployment runs all known
heads first and then uses this idempotent compatibility provisioner. It only
creates missing exchange tables and never rebuilds existing school data.
"""

from database.base import Base
from database.session import engine
from database.multi_tenant_school_management.models.learning_material import (
    LearningMaterial,
    LearningMaterialApproval,
)
from database.multi_tenant_school_management.models.student_transfer import StudentTransfer


TABLES = [
    StudentTransfer.__table__,
    LearningMaterial.__table__,
    LearningMaterialApproval.__table__,
]


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine, tables=TABLES, checkfirst=True)
    print("Tutor transfer and cross-school learning exchange schema is ready.")
