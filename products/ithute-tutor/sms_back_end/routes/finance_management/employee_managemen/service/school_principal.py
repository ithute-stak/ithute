from uuid import UUID

from fastapi import HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session, joinedload

from database.multi_tenant_school_management.models import (
    Principal,
    User,
    Person,
    Employee,
)
from database.multi_tenant_school_management.schemas.user import UserRole
from utils.auth.password_hash_verify import hash_password
from utils.generate_emp_number import generate_employee_number


class PrincipalService:

    @staticmethod
    def _principal_query(db: Session):
        return (
            db.query(Principal)
            .options(
                joinedload(Principal.user).joinedload(User.person),
                joinedload(Principal.employee),
                joinedload(Principal.school),
            )
        )

    @staticmethod
    def create_principal(db: Session, payload):
        existing_principal = (
            db.query(Principal)
            .filter(Principal.school_id == payload.school_id)
            .first()
        )

        if existing_principal:
            raise HTTPException(
                status_code=400,
                detail="This school already has a principal",
            )

        existing_user = (
            db.query(User)
            .filter(User.email == payload.user.email)
            .first()
        )

        if existing_user:
            raise HTTPException(
                status_code=400,
                detail="Email already exists",
            )

        user = User(
            username=payload.user.username,
            email=payload.user.email,
            password=hash_password(payload.user.password),
            role=UserRole.principal,
            school_id=payload.school_id,
        )

        db.add(user)
        db.flush()

        person = Person(
            id=user.id,
            **payload.user.person.model_dump(),
        )

        db.add(person)
        db.flush()

        employee = Employee(
            employee_number=f"SP-{generate_employee_number(db)}",
        )

        db.add(employee)
        db.flush()

        principal = Principal(
            school_id=payload.school_id,
            user_id=user.id,
            employee_id=employee.id,
        )

        db.add(principal)
        db.commit()
        db.refresh(principal)

        return (
            PrincipalService
            ._principal_query(db)
            .filter(Principal.id == principal.id)
            .first()
        )

    @staticmethod
    def get_all_principals(db: Session):
        return (
            PrincipalService
            ._principal_query(db)
            .order_by(Principal.created_at.desc())
            .all()
        )

    @staticmethod
    def get_principal(db: Session, principal_id: UUID):
        return (
            PrincipalService
            ._principal_query(db)
            .filter(Principal.id == principal_id)
            .first()
        )

    @staticmethod
    def get_principal_by_school(db: Session, school_id: UUID):
        return (
            PrincipalService
            ._principal_query(db)
            .filter(Principal.school_id == school_id)
            .first()
        )

    @staticmethod
    def delete_principal(db: Session, principal: Principal):
        db.delete(principal)
        db.commit()