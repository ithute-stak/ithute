from uuid import UUID

from fastapi import HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session, joinedload

from database.multi_tenant_school_management.models import (
    VicePrincipal,
    User,
    Person,
    Employee,
)
from database.multi_tenant_school_management.schemas.user import UserRole
from utils.auth.password_hash_verify import hash_password
from utils.generate_emp_number import generate_employee_number


class VicePrincipalService:

    @staticmethod
    def _query(db: Session):
        return (
            db.query(VicePrincipal)
            .options(
                joinedload(VicePrincipal.user).joinedload(User.person),
                joinedload(VicePrincipal.employee),
                joinedload(VicePrincipal.school),
            )
        )

    @staticmethod
    def create_vice_principal(db: Session, payload):
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
            role=UserRole.vice_principal,
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

        vice_principal = VicePrincipal(
            school_id=payload.school_id,
            user_id=user.id,
            employee_id=employee.id,
        )

        db.add(vice_principal)
        db.commit()
        db.refresh(vice_principal)

        return (
            VicePrincipalService
            ._query(db)
            .filter(VicePrincipal.id == vice_principal.id)
            .first()
        )

    @staticmethod
    def get_all(db: Session):
        return (
            VicePrincipalService
            ._query(db)
            .order_by(VicePrincipal.created_at.desc())
            .all()
        )

    @staticmethod
    def get_one(db: Session, vice_principal_id: UUID):
        return (
            VicePrincipalService
            ._query(db)
            .filter(VicePrincipal.id == vice_principal_id)
            .first()
        )

    @staticmethod
    def get_by_school(db: Session, school_id: UUID):
        return (
            VicePrincipalService
            ._query(db)
            .filter(VicePrincipal.school_id == school_id)
            .order_by(VicePrincipal.created_at.desc())
            .all()
        )

    @staticmethod
    def delete(db: Session, vice_principal: VicePrincipal):
        db.delete(vice_principal)
        db.commit()