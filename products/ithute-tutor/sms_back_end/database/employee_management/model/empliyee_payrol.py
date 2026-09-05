from sqlalchemy import (
    Column,
    String,
    Numeric,
    Integer,
    ForeignKey, UniqueConstraint
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class EmployeePayroll(Base):
    __tablename__ = "employee_payrolls"

    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=False
    )

    payroll_month = Column(String, nullable=False)

    payroll_year = Column(Integer, nullable=False)

    basic_salary = Column(
        Numeric(12, 2),
        default=0
    )

    allowances = Column(
        Numeric(12, 2),
        default=0
    )

    deductions = Column(
        Numeric(12, 2),
        default=0
    )

    gross_salary = Column(
        Numeric(12, 2),
        default=0
    )

    net_salary = Column(
        Numeric(12, 2),
        default=0
    )

    amount_paid = Column(
        Numeric(12, 2),
        default=0
    )

    balance = Column(
        Numeric(12, 2),
        default=0
    )

    status = Column(
        String,
        default="unpaid"
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================
    employee = relationship(
        "Employee",
        back_populates="payrolls"
    )

    payments = relationship(
        "EmployeePaymentAllocation",
        back_populates="payroll",
        cascade="all, delete"
    )

    __table_args__ = (
        UniqueConstraint(
            "employee_id",
            "payroll_month",
            "payroll_year",
            name="uq_employee_payroll_month_year"
        ),
    )