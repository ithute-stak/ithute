from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class Parent(Base):
    __tablename__ = "parents"

    id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

    user = relationship("User", back_populates="parent_profile")

    children = relationship(
        "ParentStudent",
        back_populates="parent",
        cascade="all, delete-orphan"
    )