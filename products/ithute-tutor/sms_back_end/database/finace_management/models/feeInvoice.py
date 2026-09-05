import uuid
from decimal import Decimal

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    UUID,
    Date,
    String, Numeric, Boolean
)

from sqlalchemy.orm import relationship

from database.base import Base


class FeeInvoice(Base):
    __tablename__ = "fee_invoices"

    academic_year = Column(String(255))

    invoice_number = Column(
        String,
        unique=True,
        nullable=False
    )

    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.id"),
        nullable=False
    )

    penalty_amount = Column(Numeric(12, 2), default=0)
    due_date = Column(Date)
    is_overdue = Column(Boolean, default=False)

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id"),
        nullable=False
    )

    fee_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fee_plans.id"),
        nullable=False
    )

    quarter = Column(String(255), nullable=True)

    description = Column(String)

    period_start = Column(Date)

    period_end = Column(Date)

    amount_due = Column(
        Numeric(12, 2),
        default=Decimal("0.00")
    )

    amount_paid = Column(
        Numeric(12, 2),
        default=Decimal("0.00")
    )

    balance = Column(
        Numeric(12, 2),
        default=Decimal("0.00")
    )

    status = Column(
        String,
        default="unpaid"
    )

    allocations = relationship(
        "FeePaymentAllocation",
        back_populates="invoice"
    )
    # unpaid | partial | paid | overdue

    # =========================
    # RELATIONSHIPS
    # =========================
    student = relationship(
        "Student",
        back_populates="fee_invoices"
    )

    fee_plan = relationship(
        "FeePlan",
        back_populates="invoices"
    )
