# routes/parent.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from database.session import get_db
from database.multi_tenant_school_management.models import Parent, User
from database.multi_tenant_school_management.schemas.parent import ParentCreate, ParentRead

router = APIRouter(prefix="/parents", tags=["Parents"])


@router.post("/", response_model=ParentRead)
def create_parent(payload: ParentCreate, db: Session = Depends(get_db)):
    user = User(**payload.user.model_dump())
    db.add(user)
    db.flush()

    parent = Parent(id=user.id)
    db.add(parent)

    db.commit()
    db.refresh(parent)
    return parent


@router.get("/{parent_id}", response_model=ParentRead)
def get_parent(parent_id: UUID, db: Session = Depends(get_db)):
    parent = db.get(Parent, parent_id)
    if not parent:
        raise HTTPException(404, "Parent not found")
    return parent