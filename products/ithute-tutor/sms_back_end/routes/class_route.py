from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import Class, SchoolClass
from database.multi_tenant_school_management.models.grade import Grade
from database.multi_tenant_school_management.schemas.class_schema import (
    ClassCreate,
    ClassDetailResponse,
    ClassResponse,
    ClassUpdate,
)
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles
from ws.broadcasting.stundent_payment import class_created_socket

router = APIRouter(prefix="/classes", tags=["Classes"])


def _school_class_query(db: Session, school_id: UUID):
    return (
        db.query(Class)
        .join(SchoolClass, SchoolClass.class_id == Class.id)
        .filter(SchoolClass.school_id == school_id)
    )


def _class_for_school(db: Session, school_id: UUID, class_id: UUID) -> Class | None:
    return _school_class_query(db, school_id).filter(Class.id == class_id).first()


@router.post("/", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
async def create_class(
    payload: ClassCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "vice_principal", "registrar")
    ),
):
    grade = db.query(Grade).filter(Grade.id == payload.grade_id).first()
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found")

    # Class/grade definitions form a shared education catalog. The school's
    # workspace owns only the assignment of that class to the school.
    classroom = (
        db.query(Class)
        .filter(Class.name == payload.name, Class.grade_id == payload.grade_id)
        .first()
    )
    if classroom is None:
        classroom = Class(**payload.model_dump())
        db.add(classroom)
        db.flush()

    existing_assignment = (
        db.query(SchoolClass)
        .filter(
            SchoolClass.school_id == context.school_id,
            SchoolClass.class_id == classroom.id,
        )
        .first()
    )
    if existing_assignment:
        raise HTTPException(status_code=409, detail="Class already exists in this school workspace")

    db.add(
        SchoolClass(
            school_id=context.school_id,
            class_id=classroom.id,
            capacity=40,
        )
    )
    db.commit()
    db.refresh(classroom)

    await class_created_socket(jsonable_encoder(classroom))
    return classroom


@router.get("/", response_model=List[ClassResponse])
def get_classes(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return _school_class_query(db, context.school_id).order_by(Class.name.asc()).all()


@router.get("/{class_id}", response_model=ClassDetailResponse)
def get_class(
    class_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    classroom = _class_for_school(db, context.school_id, class_id)
    if not classroom:
        raise HTTPException(status_code=404, detail="Class not found in this school")
    return classroom


@router.put("/{class_id}", response_model=ClassResponse)
def update_class(
    class_id: UUID,
    payload: ClassUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "vice_principal", "registrar")
    ),
):
    classroom = _class_for_school(db, context.school_id, class_id)
    if not classroom:
        raise HTTPException(status_code=404, detail="Class not found in this school")

    # Class definitions can be shared by schools. Do not mutate a shared
    # catalog row if another school also uses it; create/reuse the requested
    # catalog definition and move only this school's mapping instead.
    update_data = payload.model_dump(exclude_unset=True)
    target_name = update_data.get("name", classroom.name)
    target_grade_id = update_data.get("grade_id", classroom.grade_id)

    if target_name == classroom.name and target_grade_id == classroom.grade_id:
        return classroom

    target = (
        db.query(Class)
        .filter(Class.name == target_name, Class.grade_id == target_grade_id)
        .first()
    )
    if target is None:
        target = Class(name=target_name, grade_id=target_grade_id)
        db.add(target)
        db.flush()

    mapping = (
        db.query(SchoolClass)
        .filter(
            SchoolClass.school_id == context.school_id,
            SchoolClass.class_id == classroom.id,
        )
        .first()
    )
    if mapping is None:
        raise HTTPException(status_code=404, detail="School class mapping not found")

    duplicate = (
        db.query(SchoolClass)
        .filter(
            SchoolClass.school_id == context.school_id,
            SchoolClass.class_id == target.id,
            SchoolClass.id != mapping.id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Target class already exists in this school")

    mapping.class_id = target.id
    db.commit()
    db.refresh(target)
    return target


@router.delete("/{class_id}", status_code=status.HTTP_200_OK)
def delete_class(
    class_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "vice_principal", "registrar")
    ),
):
    mapping = (
        db.query(SchoolClass)
        .filter(
            SchoolClass.school_id == context.school_id,
            SchoolClass.class_id == class_id,
        )
        .first()
    )
    if not mapping:
        raise HTTPException(status_code=404, detail="Class not found in this school")

    # Removing a class from School A must never erase the shared catalog row
    # or another school's configuration.
    db.delete(mapping)
    db.commit()
    return {"message": "Class removed from this school workspace"}
