from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from database.employee_management.model.employee import Employee
from database.multi_tenant_school_management.models import Person, SchoolMembership, Teacher, User
from database.multi_tenant_school_management.models.enum.user_role import UserRole
from database.multi_tenant_school_management.schemas.teacher import TeacherCreate, TeacherRead
from database.session import get_db
from utils.auth.password_hash_verify import hash_password
from utils.generate_emp_number import generate_employee_number
from utils.school_context import SchoolContext, get_school_context, require_school_roles
from ws.broadcasting.stundent_payment import teacher_created_socket

router = APIRouter(prefix="/teachers", tags=["Teachers"])


@router.post("/", response_model=TeacherRead, status_code=201)
async def create_teacher(
    payload: TeacherCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(
        require_school_roles("school_admin", "principal", "vice_principal", "hr_manager")
    ),
):
    existing_user = db.query(User).filter(User.email == payload.user.email).first()
    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="This email already has a Tutor profile; link/assign the existing person instead of creating a duplicate",
        )

    try:
        user_data = payload.user.model_dump(exclude={"person", "password", "school_id", "role"})
        user = User(
            **user_data,
            school_id=context.school_id,
            role=UserRole.teacher,
            password=hash_password(payload.user.password) if payload.user.password else None,
        )
        db.add(user)
        db.flush()

        db.add(Person(**payload.user.person.model_dump(), id=user.id))
        db.flush()

        employee = Employee(
            employee_number=generate_employee_number(db),
            school_id=context.school_id,
        )
        db.add(employee)
        db.flush()

        teacher = Teacher(
            user_id=user.id,
            employee_id=employee.id,
            school_id=context.school_id,
        )
        db.add(teacher)
        db.add(
            SchoolMembership(
                user_id=user.id,
                school_id=context.school_id,
                role="teacher",
                title="Teacher",
                is_active=True,
                is_default=True,
            )
        )
        db.commit()
        db.refresh(teacher)

        await teacher_created_socket(jsonable_encoder(teacher))
        return teacher
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create teacher") from exc


@router.get("/", response_model=List[TeacherRead])
def read_teachers(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return db.query(Teacher).filter(Teacher.school_id == context.school_id).all()


@router.get("/{teacher_id}", response_model=TeacherRead)
def get_teacher(
    teacher_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    teacher = (
        db.query(Teacher)
        .filter(Teacher.id == teacher_id, Teacher.school_id == context.school_id)
        .first()
    )
    if not teacher:
        raise HTTPException(404, "Teacher not found in this school")
    return teacher
