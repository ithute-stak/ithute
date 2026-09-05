from decimal import Decimal
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database.multi_tenant_school_management.models import (
    SchoolAdmin,
    User,
    Person,
    Employee,
    Student,
    Teacher,
    Class,
    Grade,
    FeePayment,
    EmployeePayroll,
)

from database.multi_tenant_school_management.schemas.user import UserRole
from utils.auth.password_hash_verify import hash_password
from utils.generate_emp_number import generate_employee_number


class SchoolAdminService:

    @staticmethod
    def create_school_admin(db: Session, payload):
        existing_user = (
            db.query(User)
            .filter(User.email == payload.user.email)
            .first()
        )

        if existing_user:
            raise ValueError("Email already exists")

        user = User(
            username=payload.user.username,
            email=payload.user.email,
            password=hash_password(payload.user.password),
            role=UserRole.school_admin,
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
            employee_number=f"SAD-{generate_employee_number(db)}",
        )

        db.add(employee)
        db.flush()

        school_admin = SchoolAdmin(
            school_id=payload.school_id,
            user_id=user.id,
            employee_id=employee.id,
        )

        db.add(school_admin)
        db.commit()
        db.refresh(school_admin)

        return school_admin

    @staticmethod
    def get_all_school_admins(db: Session):
        return (
            db.query(SchoolAdmin)
            .options(
                joinedload(SchoolAdmin.user).joinedload(User.person),
                joinedload(SchoolAdmin.employee),
                joinedload(SchoolAdmin.school),
            )
            .order_by(SchoolAdmin.created_at.desc())
            .all()
        )

    @staticmethod
    def get_school_admin(db: Session, admin_id: UUID):
        return (
            db.query(SchoolAdmin)
            .options(
                joinedload(SchoolAdmin.user).joinedload(User.person),
                joinedload(SchoolAdmin.employee),
                joinedload(SchoolAdmin.school),
            )
            .filter(SchoolAdmin.id == admin_id)
            .first()
        )

    @staticmethod
    def get_school_admins_by_school(db: Session, school_id: UUID):
        return (
            db.query(SchoolAdmin)
            .options(
                joinedload(SchoolAdmin.user).joinedload(User.person),
                joinedload(SchoolAdmin.employee),
                joinedload(SchoolAdmin.school),
            )
            .filter(SchoolAdmin.school_id == school_id)
            .all()
        )

    @staticmethod
    def delete_school_admin(db: Session, admin: SchoolAdmin):
        db.delete(admin)
        db.commit()

    @staticmethod
    def dashboard(db: Session, school_id: UUID):
        students = (
            db.query(Student)
            .join(User, Student.id == User.id)
            .filter(User.school_id == school_id)
            .count()
        )

        teachers = (
            db.query(Teacher)
            .filter(Teacher.school_id == school_id)
            .count()
        )

        classes = db.query(Class).count()
        grades = db.query(Grade).count()

        employees = (
            db.query(Employee)
            .count()
        )

        payments = db.query(FeePayment).all()

        total_collected = sum(
            float(payment.amount_paid or 0)
            for payment in payments
        )

        payrolls = db.query(EmployeePayroll).all()

        payroll_total = sum(
            float(item.net_salary or 0)
            for item in payrolls
        )

        payroll_paid = sum(
            float(item.amount_paid or 0)
            for item in payrolls
        )

        payroll_unpaid = sum(
            float(item.balance or 0)
            for item in payrolls
        )

        return {
            "students": students,
            "teachers": teachers,
            "classes": classes,
            "grades": grades,
            "employees": employees,
            "payments_count": len(payments),
            "total_collected": total_collected,
            "payroll_total": payroll_total,
            "payroll_paid": payroll_paid,
            "payroll_unpaid": payroll_unpaid,
        }

    @staticmethod
    def finance_summary(db: Session):
        payments = db.query(FeePayment).all()

        total_collected = sum(
            float(payment.amount_paid or 0)
            for payment in payments
        )

        return {
            "total_collected": total_collected,
            "payments_count": len(payments),
            "today_collections": 0,
        }

    @staticmethod
    def payroll_summary(db: Session):
        payrolls = db.query(EmployeePayroll).all()

        total_payroll = sum(float(p.net_salary or 0) for p in payrolls)
        paid = sum(float(p.amount_paid or 0) for p in payrolls)
        unpaid = sum(float(p.balance or 0) for p in payrolls)
        partial = sum(
            float(p.balance or 0)
            for p in payrolls
            if p.status == "partial"
        )

        return {
            "total_payroll": total_payroll,
            "paid": paid,
            "unpaid": unpaid,
            "partial": partial,
        }