from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import School
from database.multi_tenant_school_management.schemas.school import SchoolCreate, SchoolUpdate


def create_school(db: Session, data: SchoolCreate) -> School:
    payload = data.model_dump()

    for field_name in ("school_code", "registration_number", "slug"):
        value = payload.get(field_name)
        if not value:
            continue
        existing = db.execute(select(School).where(getattr(School, field_name) == value)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail=f"{field_name.replace('_', ' ').title()} already exists")

    # Registration is an independently verified platform status. Supplying a
    # registration number does not self-certify the school.
    payload["is_registered"] = False
    payload["is_active"] = True

    school = School(**payload)
    db.add(school)
    db.flush()
    return school


def get_school(db: Session, school_id: UUID) -> School | None:
    return db.query(School).filter(School.id == school_id).first()


def get_schools(db: Session) -> list[School]:
    return db.query(School).order_by(School.name.asc()).all()


def update_school(db: Session, school: School, data: SchoolUpdate) -> School:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(school, key, value)
    db.commit()
    db.refresh(school)
    return school


def delete_school(db: Session, school: School):
    db.delete(school)
    db.commit()
