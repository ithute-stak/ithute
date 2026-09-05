from sqlalchemy import (
    Column,
    String,
    Numeric,
    Boolean,
    ForeignKey
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class EmployeeSalaryStructure(Base):
    __tablename__ = "employee_salary_structures"

    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=False
    )

    basic_salary = Column(
        Numeric(12, 2),
        default=0
    )

    housing_allowance = Column(
        Numeric(12, 2),
        default=0
    )

    transport_allowance = Column(
        Numeric(12, 2),
        default=0
    )

    medical_allowance = Column(
        Numeric(12, 2),
        default=0
    )

    overtime_allowance = Column(
        Numeric(12, 2),
        default=0
    )

    other_allowance = Column(
        Numeric(12, 2),
        default=0
    )

    tax_percentage = Column(
        Numeric(5, 2),
        default=0
    )

    pension_percentage = Column(
        Numeric(5, 2),
        default=0
    )

    active = Column(
        Boolean,
        default=True
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================
    employee = relationship(
        "Employee",
        back_populates="salary_structure"
    )