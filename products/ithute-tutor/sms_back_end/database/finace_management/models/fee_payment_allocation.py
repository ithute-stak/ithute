from sqlalchemy import Column, UUID, ForeignKey, Numeric
from sqlalchemy.orm import relationship

from database.base import Base


# =========================================================
# PAYMENT ALLOCATION
# =========================================================

class FeePaymentAllocation(Base):
    __tablename__ = "fee_payment_allocations"

    payment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fee_payments.id"),
        nullable=False
    )

    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fee_invoices.id"),
        nullable=False
    )

    amount_allocated = Column(
        Numeric(12, 2),
        nullable=False
    )

    payment = relationship(
        "FeePayment",
        back_populates="allocations"
    )

    invoice = relationship(
        "FeeInvoice",
        back_populates="allocations"
    )