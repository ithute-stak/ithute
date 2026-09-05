from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class Student(Base):
    __tablename__ = "students"

    id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

    admission_number = Column(String(255), unique=True, nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)

    user = relationship("User", back_populates="student_profile")
    classroom = relationship("Class", back_populates="students")

    parents = relationship("ParentStudent", back_populates="student", cascade="all, delete-orphan")
    enrollments = relationship("StudentEnrollment", back_populates="student", cascade="all, delete-orphan")
    attendance_records = relationship(
        "StudentAttendance",
        back_populates="student",
        cascade="all, delete"
    )
    fee_invoices = relationship(
        "FeeInvoice",
        back_populates="student"
    )

    fee_payments = relationship(
        "FeePayment",
        back_populates="student"
    )

    credits = relationship(
        "StudentCredit",
        back_populates="student",
        cascade="all, delete-orphan"
    )