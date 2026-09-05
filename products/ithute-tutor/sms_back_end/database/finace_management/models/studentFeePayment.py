from sqlalchemy import Column, ForeignKey, Numeric, String, UUID
from sqlalchemy.orm import relationship

from database.base import Base


class FeePayment(Base):
    __tablename__ = "fee_payments"

    # A learner can move between schools, so a payment must permanently keep
    # the school that received it instead of inferring ownership from the
    # learner's current enrollment later.
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="RESTRICT"),
        nullable=True,  # nullable only for ambiguous legacy rows
        index=True,
    )

    student_id = Column(
        UUID(as_uuid=True),
        ForeignKey("students.id"),
        nullable=False,
    )

    amount_paid = Column(Numeric(12, 2), nullable=False)

    payment_number = Column(
        String(16),
        nullable=False,
        unique=True,
    )

    payment_method = Column(String)
    reference = Column(String)

    school = relationship("School")

    allocations = relationship(
        "FeePaymentAllocation",
        back_populates="payment",
    )

    student = relationship(
        "Student",
        back_populates="fee_payments",
    )

    credits = relationship(
        "StudentCredit",
        back_populates="source_payment",
    )
