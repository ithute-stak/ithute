from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class HardwareTelemetrySnapshot(Base):
    __tablename__ = "hardware_telemetry_snapshots"
    __table_args__ = (
        UniqueConstraint("nonce", name="uq_hardware_telemetry_nonce"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("infrastructure_servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(32), nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, nullable=False)
    health_status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_pressure_avg10: Mapped[float | None] = mapped_column(Float, nullable=True)
    io_pressure_avg10: Mapped[float | None] = mapped_column(Float, nullable=True)
    filesystem_used_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    predictive_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predictive_state: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    predictive_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    predictive_evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
