from uuid import UUID

from sqlalchemy.orm import Session

from database.finace_management.models.feeConfigurations import SchoolFeeConfiguration
from database.finace_management.models.feePlan import FeePlan
from database.finace_management.schemas.feePlan import FeePlanCreate, FeePlanUpdate


def _school_plan_query(db: Session, school_id: UUID):
    return (
        db.query(FeePlan)
        .join(SchoolFeeConfiguration, SchoolFeeConfiguration.id == FeePlan.feeConfig_id)
        .filter(SchoolFeeConfiguration.school_id == school_id)
    )


def create_fee_plan(db: Session, payload: FeePlanCreate, school_id: UUID):
    config = (
        db.query(SchoolFeeConfiguration)
        .filter(
            SchoolFeeConfiguration.id == payload.feeConfig_id,
            SchoolFeeConfiguration.school_id == school_id,
        )
        .first()
    )
    if config is None:
        return None
    plan = FeePlan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def get_fee_plans(db: Session, school_id: UUID):
    return _school_plan_query(db, school_id).all()


def get_fee_plan(db: Session, plan_id: UUID, school_id: UUID):
    return _school_plan_query(db, school_id).filter(FeePlan.id == plan_id).first()


def update_fee_plan(db: Session, plan_id: UUID, payload: FeePlanUpdate, school_id: UUID):
    plan = get_fee_plan(db, plan_id, school_id)
    if not plan:
        return None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(plan, key, value)
    db.commit()
    db.refresh(plan)
    return plan


def delete_fee_plan(db: Session, plan_id: UUID, school_id: UUID):
    plan = get_fee_plan(db, plan_id, school_id)
    if not plan:
        return None
    db.delete(plan)
    db.commit()
    return plan
