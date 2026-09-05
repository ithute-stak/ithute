from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey
)

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class EmployeePayment(Base):
    __tablename__ = "employee_payments"

    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=False
    )

    amount_paid = Column(
        Numeric(12, 2),
        nullable=False
    )

    payment_method = Column(
        String,
        default="cash"
    )

    reference = Column(String)

    payment_number = Column(
        String,
        unique=True
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================
    employee = relationship(
        "Employee",
        back_populates="payments"
    )

    allocations = relationship(
        "EmployeePaymentAllocation",
        back_populates="payment",
        cascade="all, delete"
    )