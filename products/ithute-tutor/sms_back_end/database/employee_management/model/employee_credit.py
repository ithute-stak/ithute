from sqlalchemy import (
    Column,
    Numeric,
    ForeignKey
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class EmployeeCredit(Base):
    __tablename__ = "employee_credits"

    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=False
    )

    amount = Column(
        Numeric(12, 2),
        default=0
    )

    source_payment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employee_payments.id")
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================
    employee = relationship(
        "Employee",
        back_populates="credits"
    )

    source_payment = relationship(
        "EmployeePayment"
    )