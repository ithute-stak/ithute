import enum
from sqlalchemy import Column, String, Date, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class GenderEnum(str, enum.Enum):
    male = "male"
    female = "female"
    other = "other"


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)

    gender = Column(Enum(GenderEnum), nullable=False)
    date_of_birth = Column(Date, nullable=False)

    nationality = Column(String(100), nullable=False)
    national_id = Column(String(100), unique=True, nullable=True)

    user = relationship("User", back_populates="person")