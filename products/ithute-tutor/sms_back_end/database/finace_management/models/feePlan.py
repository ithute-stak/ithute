import uuid

from sqlalchemy import (
    Column,
    String,
    Float,
    ForeignKey,
    UUID
)

from sqlalchemy.orm import relationship

from database.base import Base


class FeePlan(Base):

    __tablename__ = "fee_plans"

    feeConfig_id = Column(
        UUID(as_uuid=True),
        ForeignKey("school_fee_configuration.id"),
        nullable=False
    )

    grade_id = Column(
        UUID(as_uuid=True),
        ForeignKey("grades.id"),
        nullable=False
    )

    name = Column(
        String,
        nullable=False
    )
    # e.g. "Grade 1 Package"

    first_quarter = Column(
        Float,
        nullable=False
    )
    second_quarter = Column(
        Float,
        nullable=False
    )
    third_quarter = Column(
        Float,
        nullable=False
    )
    fourth_quarter =Column(
        Float,
        nullable=False
    )

    description = Column(
        String,
        nullable=True
    )

    # =========================
    # RELATIONSHIPS
    # =========================
    feeConfig = relationship(
        "SchoolFeeConfiguration",
        back_populates="fee_plan"
    )

    grade = relationship(
        "Grade",
        back_populates="fee_plans"
    )

    invoices = relationship(
        "FeeInvoice",
        back_populates="fee_plan"
    )