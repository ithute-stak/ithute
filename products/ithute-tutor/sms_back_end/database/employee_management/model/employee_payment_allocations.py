from sqlalchemy import (
    Column,
    Numeric,
    ForeignKey
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class EmployeePaymentAllocation(Base):
    __tablename__ = "employee_payment_allocations"

    payment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employee_payments.id"),
        nullable=False
    )

    payroll_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employee_payrolls.id"),
        nullable=False
    )

    amount_allocated = Column(
        Numeric(12, 2),
        nullable=False
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================
    payment = relationship(
        "EmployeePayment",
        back_populates="allocations"
    )

    payroll = relationship(
        "EmployeePayroll",
        back_populates="payments"
    )