from datetime import datetime,timezone
from sqlalchemy import DateTime,ForeignKey,Integer,JSON,String,Text
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base
def now():return datetime.now(timezone.utc)
class AutomationRule(Base):
 __tablename__="automation_rules";id:Mapped[int]=mapped_column(Integer,primary_key=True);company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True);branch_id:Mapped[int|None]=mapped_column(ForeignKey("branches.id",ondelete="CASCADE"),index=True);name:Mapped[str]=mapped_column(String(160));trigger:Mapped[str]=mapped_column(String(80));channel:Mapped[str]=mapped_column(String(40));status:Mapped[str]=mapped_column(String(24),default="active",index=True);created_by:Mapped[str]=mapped_column(String(255));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class AutomationAuditEvent(Base):
 __tablename__="automation_audit_events";id:Mapped[int]=mapped_column(Integer,primary_key=True);company_id:Mapped[int]=mapped_column(ForeignKey("companies.id",ondelete="CASCADE"),index=True);branch_id:Mapped[int|None]=mapped_column(ForeignKey("branches.id",ondelete="SET NULL"),index=True);actor:Mapped[str]=mapped_column(String(255));action:Mapped[str]=mapped_column(String(120));detail:Mapped[dict]=mapped_column(JSON,default=dict);occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
