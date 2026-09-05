from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class ParentStudent(Base):
    __tablename__ = "parent_students"

    parent_id = Column(UUID(as_uuid=True), ForeignKey("parents.id"), primary_key=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), primary_key=True)

    parent = relationship("Parent", back_populates="children")
    student = relationship("Student", back_populates="parents")

    __table_args__ = (
        UniqueConstraint("parent_id", "student_id", name="uix_parent_student"),
    )