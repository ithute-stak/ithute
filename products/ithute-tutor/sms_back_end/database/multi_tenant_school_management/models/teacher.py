from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class Teacher(Base):
    __tablename__ = "teachers"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id"),
        nullable=False
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        unique=True
    )

    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        unique=True,
        nullable=False
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    user = relationship(
        "User",
        back_populates="teacher"
    )

    employee = relationship(
        "Employee",
        back_populates="teacher"
    )

    school = relationship(
        "School"
    )