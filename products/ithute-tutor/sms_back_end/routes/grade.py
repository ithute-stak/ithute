from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models.grade import Grade
from database.multi_tenant_school_management.schemas.grade import (
    GradeCreate,
    GradeDetailResponse,
    GradeResponse,
    GradeUpdate,
)
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context
from ws.broadcasting.stundent_payment import grade_created_socket

router = APIRouter(prefix="/grades", tags=["Grades"])


def _require_platform_admin(context: SchoolContext) -> None:
    if not context.is_platform_admin:
        raise HTTPException(
            status_code=403,
            detail="grade definitions are managed by the !thute Tutor platform",
        )


@router.post("/", response_model=GradeResponse, status_code=status.HTTP_201_CREATED)
async def create_grade(
    payload: GradeCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_platform_admin(context)

    existing = db.query(Grade).filter(Grade.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Grade already exists")

    new_grade = Grade(**payload.model_dump())
    db.add(new_grade)
    db.commit()
    db.refresh(new_grade)

    await grade_created_socket(jsonable_encoder(new_grade))
    return new_grade


@router.get("/", response_model=List[GradeResponse])
def get_grades(
    db: Session = Depends(get_db),
    _context: SchoolContext = Depends(get_school_context),
):
    # Grades are shared reference data (for example Grade 1..12). Seeing the
    # catalog does not expose another school's business data.
    return db.query(Grade).order_by(Grade.name.asc()).all()


@router.get("/{grade_id}", response_model=GradeDetailResponse)
def get_grade(
    grade_id: UUID,
    db: Session = Depends(get_db),
    _context: SchoolContext = Depends(get_school_context),
):
    grade = db.query(Grade).filter(Grade.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")
    return grade


@router.put("/{grade_id}", response_model=GradeResponse)
def update_grade(
    grade_id: UUID,
    payload: GradeUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_platform_admin(context)

    grade = db.query(Grade).filter(Grade.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(grade, key, value)

    db.commit()
    db.refresh(grade)
    return grade


@router.delete("/{grade_id}", status_code=status.HTTP_200_OK)
def delete_grade(
    grade_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_platform_admin(context)

    grade = db.query(Grade).filter(Grade.id == grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    db.delete(grade)
    db.commit()
    return {"message": "Grade deleted successfully"}
