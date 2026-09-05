from uuid import uuid4
from decimal import Decimal

from sqlalchemy import Column, Numeric, ForeignKey, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime

from database.base import Base
from datetime import datetime

class StudentCredit(Base):
    __tablename__ = "student_credits"
    academic_year = Column(String(255))
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"))
    source_payment_id = Column(UUID(as_uuid=True), ForeignKey("fee_payments.id"))

    amount = Column(Numeric(12,2))

    created_at = Column(DateTime, default=datetime.utcnow)

    student = relationship("Student", back_populates="credits")
    source_payment = relationship("FeePayment", back_populates="credits")