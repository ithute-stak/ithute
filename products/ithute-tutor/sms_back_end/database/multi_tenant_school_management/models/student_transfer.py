from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, JSON, String, Text, UUID
from sqlalchemy.orm import relationship

from database.base import Base


class StudentTransfer(Base):
    __tablename__ = "student_transfers"

    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    source_school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    destination_school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="SET NULL"), nullable=True, index=True)

    # Human-readable reference for school correspondence and audit follow-up.
    reference_number = Column(String(40), nullable=True, unique=True, index=True)

    # The one-time code is a secure claim token. It does not itself complete a
    # transfer; the receiving school must claim, review, then accept/reject.
    code_hash = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="released", index=True)
    # released | under_review | accepted | rejected | cancelled | expired

    transfer_reason = Column(String(80), nullable=True)
    note = Column(String(500), nullable=True)  # source-school handover note (legacy-compatible)
    destination_note = Column(String(1000), nullable=True)
    rejection_reason = Column(String(1000), nullable=True)

    consent_confirmed = Column(Boolean, nullable=False, default=False)
    records_verified = Column(Boolean, nullable=False, default=False)

    expires_at = Column(DateTime, nullable=False)
    proposed_start_date = Column(Date, nullable=True)
    destination_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)

    released_at = Column(DateTime, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    released_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    claimed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    accepted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancelled_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    events = relationship(
        "StudentTransferEvent",
        back_populates="transfer",
        cascade="all, delete-orphan",
        order_by="StudentTransferEvent.created_at.asc()",
    )


class StudentTransferEvent(Base):
    __tablename__ = "student_transfer_events"

    transfer_id = Column(UUID(as_uuid=True), ForeignKey("student_transfers.id", ondelete="CASCADE"), nullable=False, index=True)
    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(40), nullable=False, index=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=True)
    note = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False, default=dict)

    transfer = relationship("StudentTransfer", back_populates="events")
