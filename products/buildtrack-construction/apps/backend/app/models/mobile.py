from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
def utcnow()->datetime:return datetime.now(timezone.utc)
class OfflineFieldSubmission(Base):
    __tablename__="offline_field_submissions"
    __table_args__=(UniqueConstraint("company_id","device_id","client_submission_id",name="uq_offline_submission_device_client"),)
    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),nullable=False,index=True)
    branch_id:Mapped[int]=mapped_column(ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False,index=True)
    site_id:Mapped[int]=mapped_column(ForeignKey("sites.id",ondelete="RESTRICT"),nullable=False,index=True)
    project_id:Mapped[int]=mapped_column(ForeignKey("projects.id",ondelete="CASCADE"),nullable=False,index=True)
    device_id:Mapped[str]=mapped_column(String(120),nullable=False,index=True)
    client_submission_id:Mapped[str]=mapped_column(String(120),nullable=False)
    submission_type:Mapped[str]=mapped_column(String(48),nullable=False,index=True)
    captured_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,index=True)
    payload:Mapped[dict]=mapped_column(JSON,nullable=False,default=dict)
    status:Mapped[str]=mapped_column(String(24),nullable=False,default="pending_review",index=True)
    reviewer_note:Mapped[str|None]=mapped_column(Text)
    received_by:Mapped[str]=mapped_column(String(255),nullable=False)
    received_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)
    reviewed_by:Mapped[str|None]=mapped_column(String(255))
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
