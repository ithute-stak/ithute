from sqlalchemy import Column, String, ForeignKey, UUID, UniqueConstraint
from sqlalchemy.orm import relationship
from database.base import Base


class Grade(Base):
    __tablename__ = "grades"

    name = Column(String(100), nullable=False)
    # Example: Grade 1, Grade 2, Form 1, Form 2

    classes = relationship(
        "Class",
        back_populates="grade",
        cascade="all, delete"
    )
    subjects = relationship("SchoolGradeSubject", back_populates="grade", cascade="all, delete")


    fee_plans = relationship(
        "FeePlan",
        back_populates="grade"
    )
