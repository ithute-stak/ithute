from sqlalchemy import (
    Column,
    Boolean,
    ForeignKey,
    Date,
    Enum,
    UUID
)

from sqlalchemy.orm import relationship

from database.base import Base

from database.finace_management.enum.paymentModules import (
    FeeStructureType
)
from database.finace_management.models.feePlan import FeePlan


class SchoolFeeConfiguration(Base):

    __tablename__ = "school_fee_configuration"

    school_id = Column(
        UUID(as_uuid=True),
        ForeignKey("schools.id"),
        nullable=False,
        unique=True
    )

    # =========================
    # ACADEMIC YEAR
    # =========================
    year_start = Column(Date, nullable=False)

    year_end = Column(Date, nullable=False)

    # =========================
    # PAYMENT STRUCTURE
    # =========================
    fee_structure = Column(
        Enum(FeeStructureType),
        nullable=False
    )

    allow_partial_payments = Column(
        Boolean,
        default=True
    )

    allow_late_payments = Column(
        Boolean,
        default=True
    )

    # =========================
    # RELATIONSHIP
    # =========================
    school = relationship(
        "School",
        back_populates="fee_configuration"
    )

    fee_plan = relationship(
        FeePlan,
        back_populates="feeConfig"
    )