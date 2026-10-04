from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class InfrastructureServer(Base):
    """Physical or virtual server registered once in the Ithute control plane.

    Mail and hosting nodes remain separate workload boundaries, but they can be
    linked to one infrastructure server so the owner can monitor one machine
    from a single place without duplicating the physical VPS record.
    """

    __tablename__ = "infrastructure_servers"
    __table_args__ = (
        UniqueConstraint("hostname", name="uq_infrastructure_server_hostname"),
        UniqueConstraint("mail_node_id", name="uq_infrastructure_server_mail_node"),
        UniqueConstraint("hosting_node_id", name="uq_infrastructure_server_hosting_node"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    hostname: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    public_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str] = mapped_column(String(80), default="lesotho", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    roles_json: Mapped[str] = mapped_column(Text, default='["application"]', nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    mail_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("mail_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    hosting_node_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hosting_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
