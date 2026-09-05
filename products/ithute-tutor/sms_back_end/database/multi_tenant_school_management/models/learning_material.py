from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    UUID,
    func,
)
from sqlalchemy.orm import relationship

from database.base import Base


class LearningMaterial(Base):
    __tablename__ = "learning_materials"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    grade_id = Column(
        UUID(as_uuid=True),
        ForeignKey("grades.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subject_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title = Column(String(220), nullable=False)
    description = Column(String(1000), nullable=True)
    content_type = Column(String(32), nullable=False, default="note")
    body = Column(Text, nullable=True)
    resource_url = Column(String(2000), nullable=True)

    # school: visible only inside the owning school workspace.
    # public: eligible for the shared Tutor library after moderation.
    visibility = Column(String(24), nullable=False, default="school", index=True)
    moderation_status = Column(String(24), nullable=False, default="draft", index=True)
    approval_source = Column(String(24), nullable=True)  # platform | peer
    peer_approval_threshold = Column(Integer, nullable=False, default=1)

    platform_moderated_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    platform_moderation_note = Column(String(1000), nullable=True)
    platform_moderated_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    school = relationship("School")
    author = relationship("User", foreign_keys=[author_user_id])
    grade = relationship("Grade")
    subject = relationship("Subject")
    platform_moderator = relationship("User", foreign_keys=[platform_moderated_by])
    approvals = relationship(
        "LearningMaterialApproval",
        back_populates="material",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("visibility IN ('school', 'public')", name="ck_learning_material_visibility"),
        CheckConstraint(
            "moderation_status IN ('draft', 'pending', 'approved', 'rejected', 'archived')",
            name="ck_learning_material_moderation_status",
        ),
        CheckConstraint(
            "content_type IN ('note', 'document', 'link', 'video', 'worksheet', 'lesson', 'other')",
            name="ck_learning_material_content_type",
        ),
        CheckConstraint("peer_approval_threshold >= 1", name="ck_learning_material_peer_threshold"),
        CheckConstraint("body IS NOT NULL OR resource_url IS NOT NULL", name="ck_learning_material_has_content"),
    )


class LearningMaterialApproval(Base):
    __tablename__ = "learning_material_approvals"

    material_id = Column(
        UUID(as_uuid=True),
        ForeignKey("learning_materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    note = Column(String(1000), nullable=True)
    approved_at = Column(DateTime, nullable=False, server_default=func.now())

    material = relationship("LearningMaterial", back_populates="approvals")
    school = relationship("School")
    approver = relationship("User")

    __table_args__ = (
        UniqueConstraint("material_id", "school_id", name="uq_learning_material_approval_school"),
    )
