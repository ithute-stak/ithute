from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class Employee(Base):
    __tablename__ = "employees"

    # Employment belongs to one school workspace even though the person's
    # central !thute identity may participate in more than one school.
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=True,  # nullable only during legacy-data backfill
        index=True,
    )

    employee_number = Column(String(30), nullable=True)

    school = relationship("School")

    salary_structure = relationship(
        "EmployeeSalaryStructure",
        back_populates="employee",
        uselist=False
    )

    payrolls = relationship(
        "EmployeePayroll",
        back_populates="employee",
        cascade="all, delete"
    )

    payments = relationship(
        "EmployeePayment",
        back_populates="employee",
        cascade="all, delete"
    )

    credits = relationship(
        "EmployeeCredit",
        back_populates="employee",
        cascade="all, delete"
    )

    teacher = relationship(
        "Teacher",
        back_populates="employee",
        uselist=False
    )

    school_admin = relationship(
        "SchoolAdmin",
        back_populates="employee",
        uselist=False
    )

    principal = relationship(
        "Principal",
        back_populates="employee",
        uselist=False
    )

    vice_principal = relationship(
        "VicePrincipal",
        back_populates="employee",
        uselist=False,
    )
