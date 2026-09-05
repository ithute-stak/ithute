from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class SchoolProprietor(Base):
    __tablename__ = "school_proprietors"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id"),
        nullable=False,
        unique=True
    )

    full_name = Column(String(255), nullable=False)
    national_id = Column(String(100), nullable=True)
    phone = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(255), nullable=False)

    school = relationship(
        "School",
        back_populates="proprietor"
    )