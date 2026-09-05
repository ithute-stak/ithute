import uuid
from sqlalchemy import Column, String, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base
from database.multi_tenant_school_management.schemas.user import UserRole


class User(Base):
    __tablename__ = "users"

    # Immutable cross-product identity from !thute Auth (OIDC/JWT sub).
    # It is nullable during migration so existing Tutor users are never linked
    # merely because an email/phone happens to match a central account.
    auth_user_id = Column(UUID(as_uuid=True), unique=True, index=True, nullable=True)

    username = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=True)  # legacy migration/linking credential only
    channel = Column(String(255))
    role = Column(Enum(UserRole), nullable=False, index=True)

    # Transitional/default workspace only. New authorization uses
    # SchoolMembership so one central person can belong to multiple schools.
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id"), nullable=True)

    school = relationship("School", back_populates="users")
    school_memberships = relationship(
        "SchoolMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    person = relationship(
        "Person",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    student_profile = relationship("Student", back_populates="user", uselist=False)
    parent_profile = relationship("Parent", back_populates="user", uselist=False)
    teacher = relationship("Teacher", back_populates="user", uselist=False)

    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    school_admin = relationship(
        "SchoolAdmin",
        back_populates="user",
        uselist=False
    )
    principal = relationship(
        "Principal",
        back_populates="user",
        uselist=False
    )

    vice_principal = relationship(
        "VicePrincipal",
        back_populates="user",
        uselist=False,
    )
