from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class VicePrincipal(Base):
    __tablename__ = "vice_principals"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id"),
        nullable=False,
    )

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        unique=True,
    )

    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id"),
        nullable=False,
        unique=True,
    )

    user = relationship(
        "User",
        back_populates="vice_principal",
    )

    employee = relationship(
        "Employee",
        back_populates="vice_principal",
    )

    school = relationship(
        "School",
        back_populates="vice_principals",
    )