from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from database.base import Base

class Subject(Base):
    __tablename__ = "subjects"

    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255), nullable=True)

    # relationships
    grade_links = relationship("SchoolGradeSubject", back_populates="subject", cascade="all, delete")