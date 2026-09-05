from sqlalchemy import Boolean, Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.base import Base


class SchoolMembership(Base):
    """A user's role inside one school workspace.

    Central !thute Auth owns identity. Tutor memberships own school-specific
    authorization. A single person may therefore belong to multiple schools
    with different roles while each active workspace stays isolated.
    """

    __tablename__ = "school_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "school_id", name="uq_school_membership_user_school"),
    )

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(64), nullable=False, index=True)
    title = Column(String(120), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_default = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="school_memberships")
    school = relationship("School", back_populates="memberships")
