from sqlalchemy import Column, UUID, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from database.base import Base


class SchoolClass(Base):
    __tablename__ = "school_class"
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    capacity = Column(Integer, nullable=False)
    school = relationship("School", back_populates="school_classes")
    class_ = relationship("Class", back_populates="school_classes")
    __table_args__ = (
        UniqueConstraint("school_id", "class_id"),
    )