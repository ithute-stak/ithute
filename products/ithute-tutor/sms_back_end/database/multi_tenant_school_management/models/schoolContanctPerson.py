from sqlalchemy import Column, UUID, String, ForeignKey
from sqlalchemy.orm import relationship

from database.base import Base


class SchoolContactPerson(Base):
    __tablename__ = "school_contact_persons"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id"),
        nullable=False,
        unique=True
    )

    full_name = Column(String(255), nullable=False)
    designation = Column(String(255), nullable=False)
    phone = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(255), nullable=False)

    school = relationship(
        "School",
        back_populates="contact_person"
    )