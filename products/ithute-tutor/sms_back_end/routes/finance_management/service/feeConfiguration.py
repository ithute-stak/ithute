from uuid import UUID

from sqlalchemy.orm import Session

from database.finace_management.models.feeConfigurations import SchoolFeeConfiguration
from database.finace_management.schemas.school_fee_configuration import (
    SchoolFeeConfigurationCreate,
    SchoolFeeConfigurationUpdate,
)


def create_school_fee_configuration(
    db: Session,
    payload: SchoolFeeConfigurationCreate,
    school_id: UUID,
):
    config = SchoolFeeConfiguration(
        **payload.model_dump(exclude={"school_id"}),
        school_id=school_id,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def get_school_fee_configurations(db: Session, school_id: UUID):
    return (
        db.query(SchoolFeeConfiguration)
        .filter(SchoolFeeConfiguration.school_id == school_id)
        .all()
    )


def get_school_fee_configuration(db: Session, config_id: UUID, school_id: UUID):
    return (
        db.query(SchoolFeeConfiguration)
        .filter(
            SchoolFeeConfiguration.id == config_id,
            SchoolFeeConfiguration.school_id == school_id,
        )
        .first()
    )


def update_school_fee_configuration(
    db: Session,
    config_id: UUID,
    payload: SchoolFeeConfigurationUpdate,
    school_id: UUID,
):
    config = get_school_fee_configuration(db, config_id, school_id)
    if not config:
        return None

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, key, value)
    db.commit()
    db.refresh(config)
    return config


def delete_school_fee_configuration(db: Session, config_id: UUID, school_id: UUID):
    config = get_school_fee_configuration(db, config_id, school_id)
    if not config:
        return None
    db.delete(config)
    db.commit()
    return config
