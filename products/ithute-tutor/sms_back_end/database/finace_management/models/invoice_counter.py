from sqlalchemy import Column, String, Integer

from database.base import Base


class InvoiceCounter(Base):
    __tablename__ = "invoice_counters"
    year = Column(String, unique=True, nullable=False)
    last_number = Column(Integer, default=0)