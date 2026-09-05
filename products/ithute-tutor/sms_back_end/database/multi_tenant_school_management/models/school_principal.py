from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class Principal(Base):
    __tablename__ = "principals"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id"),
        nullable=False,
        unique=True
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
        nullable=False,
        unique=True
    )

    # =====================================================
    # RELATIONSHIPS
    # =====================================================

    user = relationship(
        "User",
        back_populates="principal"
    )

    employee = relationship(
        "Employee",
        back_populates="principal"
    )

    school = relationship(
        "School",
        back_populates="principal"
    )