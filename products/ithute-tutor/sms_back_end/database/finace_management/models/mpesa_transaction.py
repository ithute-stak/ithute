from sqlalchemy import Column, String, Float
from database.base import Base

class MpesaTransaction(Base):
    __tablename__ = "mpesa_transactions"

    student_id = Column(String, nullable=False)
    conversation_id = Column(String, unique=True, nullable=False)
    transaction_reference = Column(String, unique=True, nullable=False)

    amount = Column(Float, nullable=False)
    phone = Column(String, nullable=False)

    status = Column(String, default="PENDING")
    mpesa_transaction_id = Column(String, nullable=True)


