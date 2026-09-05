from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from database.session import get_db
from database.multi_tenant_school_management.models import Person, User
from database.multi_tenant_school_management.schemas.person import PersonCreate, PersonRead, PersonUpdate

router = APIRouter(prefix="/persons", tags=["Persons"])


@router.post("/", response_model=List[PersonRead])
def get_all_person(db: Session = Depends(get_db)):
    return db.query(Person).all()


@router.get("/{person_id}", response_model=PersonRead)
def get_person(person_id: UUID, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    return person


@router.put("/{person_id}", response_model=PersonRead)
def update_person(person_id: UUID, payload: PersonUpdate, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, key, value)

    db.commit()
    db.refresh(person)
    return person


@router.delete("/{person_id}")
def delete_person(person_id: UUID, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")

    db.delete(person)
    db.commit()
    return {"message": "Deleted"}