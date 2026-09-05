from sqlalchemy import Boolean, Column, Enum, JSON, String, Text
from sqlalchemy.orm import relationship

from database.base import Base
from database.multi_tenant_school_management.models.enum.school_cat import SchoolCategory


class School(Base):
    __tablename__ = "schools"

    # Identity / registry
    name = Column(String(255), nullable=False, unique=True)
    slug = Column(String(120), nullable=True, unique=True, index=True)
    school_code = Column(String(100), unique=True, nullable=True)
    registration_number = Column(String(100), unique=True, nullable=True)
    category = Column(Enum(SchoolCategory), nullable=False)

    # Registration / lifecycle
    is_registered = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    certificate_number = Column(String(255), nullable=True)

    # School-owned profile / branding. These values make the workspace look and
    # behave like the school's own installation while remaining on one platform.
    logo_url = Column(String(1000), nullable=True)
    motto = Column(String(500), nullable=True)
    primary_color = Column(String(32), nullable=True)
    secondary_color = Column(String(32), nullable=True)
    accent_color = Column(String(32), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(80), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    timezone = Column(String(80), nullable=False, default="Africa/Maseru")
    currency = Column(String(8), nullable=False, default="LSL")
    locale = Column(String(20), nullable=False, default="en-LS")
    settings_json = Column(JSON, nullable=False, default=dict)

    users = relationship("User", back_populates="school")
    memberships = relationship(
        "SchoolMembership",
        back_populates="school",
        cascade="all, delete-orphan",
    )
    proprietor = relationship(
        "SchoolProprietor",
        back_populates="school",
        uselist=False
    )
    contact_person = relationship(
        "SchoolContactPerson",
        back_populates="school",
        uselist=False
    )
    fee_configuration = relationship(
        "SchoolFeeConfiguration",
        back_populates="school",
        uselist=False
    )
    principal = relationship(
        "Principal",
        back_populates="school",
        uselist=False
    )
    school_admin = relationship(
        "SchoolAdmin",
        back_populates="school",
        uselist=False
    )
    vice_principals = relationship(
        "VicePrincipal",
        back_populates="school",
        cascade="all, delete",
    )
    school_classes = relationship(
        "SchoolClass",
        back_populates="school",
        cascade="all, delete-orphan"
    )
    grade_subjects = relationship("SchoolGradeSubject", back_populates="school", cascade="all, delete")
