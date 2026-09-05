from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.employee_management.schemas.school_admin import (
    FinanceSummary,
    PayrollSummary,
    SchoolAdminCreate,
    SchoolAdminDashboardKpi,
    SchoolAdminRead,
)
from database.multi_tenant_school_management.models import (
    Class,
    Employee,
    EmployeePayroll,
    FeePayment,
    Grade,
    SchoolAdmin,
    SchoolClass,
    SchoolMembership,
    Student,
    StudentEnrollment,
    Teacher,
)
from database.session import get_db
from routes.finance_management.employee_managemen.service.school_admin import SchoolAdminService
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/school-admins", tags=["School Admins"])

ADMIN_ROLES = ("school_admin", "principal", "vice_principal")


def _require_requested_school(school_id: UUID, context: SchoolContext) -> None:
    if school_id != context.school_id:
        raise HTTPException(status_code=404, detail="School not found in this workspace")


def _school_payments(db: Session, school_id: UUID):
    return db.query(FeePayment).filter(FeePayment.school_id == school_id)


def _school_payrolls(db: Session, school_id: UUID):
    return (
        db.query(EmployeePayroll)
        .join(Employee, Employee.id == EmployeePayroll.employee_id)
        .filter(Employee.school_id == school_id)
    )


@router.post("/", response_model=SchoolAdminRead)
def create_school_admin(
    payload: SchoolAdminCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ADMIN_ROLES)),
):
    if payload.school_id != context.school_id:
        raise HTTPException(status_code=403, detail="Cannot create an administrator for another school")

    try:
        admin = SchoolAdminService.create_school_admin(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Complete tenant metadata for legacy service-created records.
    if admin.employee is not None:
        admin.employee.school_id = context.school_id
    membership = (
        db.query(SchoolMembership)
        .filter(
            SchoolMembership.user_id == admin.user_id,
            SchoolMembership.school_id == context.school_id,
        )
        .first()
    )
    if membership is None:
        db.add(
            SchoolMembership(
                user_id=admin.user_id,
                school_id=context.school_id,
                role="school_admin",
                title="School Administrator",
                is_active=True,
                is_default=True,
            )
        )
    db.commit()
    db.refresh(admin)
    return admin


@router.get("/", response_model=list[SchoolAdminRead])
def get_all_school_admins(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    return db.query(SchoolAdmin).filter(SchoolAdmin.school_id == context.school_id).all()


@router.get("/{admin_id}", response_model=SchoolAdminRead)
def get_school_admin(
    admin_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    admin = (
        db.query(SchoolAdmin)
        .filter(SchoolAdmin.id == admin_id, SchoolAdmin.school_id == context.school_id)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=404, detail="School admin not found in this school")
    return admin


@router.get("/school/{school_id}/admins", response_model=list[SchoolAdminRead])
def get_school_admins_by_school(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return db.query(SchoolAdmin).filter(SchoolAdmin.school_id == context.school_id).all()


@router.delete("/{admin_id}")
def delete_school_admin(
    admin_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles("school_admin", "principal")),
):
    admin = (
        db.query(SchoolAdmin)
        .filter(SchoolAdmin.id == admin_id, SchoolAdmin.school_id == context.school_id)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=404, detail="School admin not found in this school")

    SchoolAdminService.delete_school_admin(db=db, admin=admin)
    return {"message": "School admin deleted successfully"}


@router.get("/school/{school_id}/dashboard", response_model=SchoolAdminDashboardKpi)
def school_admin_dashboard(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)

    students = (
        db.query(Student)
        .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
        .filter(StudentEnrollment.school_id == context.school_id, StudentEnrollment.is_current.is_(True))
        .distinct()
        .count()
    )
    teachers = db.query(Teacher).filter(Teacher.school_id == context.school_id).count()
    classes = db.query(SchoolClass).filter(SchoolClass.school_id == context.school_id).count()
    grades = (
        db.query(Class.grade_id)
        .join(SchoolClass, SchoolClass.class_id == Class.id)
        .filter(SchoolClass.school_id == context.school_id)
        .distinct()
        .count()
    )
    employees = db.query(Employee).filter(Employee.school_id == context.school_id).count()

    payments = _school_payments(db, context.school_id).all()
    payrolls = _school_payrolls(db, context.school_id).all()

    return {
        "students": students,
        "teachers": teachers,
        "classes": classes,
        "grades": grades,
        "employees": employees,
        "payments_count": len(payments),
        "total_collected": sum(float(payment.amount_paid or 0) for payment in payments),
        "payroll_total": sum(float(item.net_salary or 0) for item in payrolls),
        "payroll_paid": sum(float(item.amount_paid or 0) for item in payrolls),
        "payroll_unpaid": sum(float(item.balance or 0) for item in payrolls),
    }


@router.get("/school/{school_id}/students")
def get_school_students(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return (
        db.query(Student)
        .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
        .filter(StudentEnrollment.school_id == context.school_id, StudentEnrollment.is_current.is_(True))
        .distinct()
        .all()
    )


@router.get("/school/{school_id}/teachers")
def get_school_teachers(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return db.query(Teacher).filter(Teacher.school_id == context.school_id).all()


@router.get("/school/{school_id}/classes")
def get_school_classes(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return (
        db.query(Class)
        .join(SchoolClass, SchoolClass.class_id == Class.id)
        .filter(SchoolClass.school_id == context.school_id)
        .all()
    )


@router.get("/school/{school_id}/grades")
def get_school_grades(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return (
        db.query(Grade)
        .join(Class, Class.grade_id == Grade.id)
        .join(SchoolClass, SchoolClass.class_id == Class.id)
        .filter(SchoolClass.school_id == context.school_id)
        .distinct()
        .all()
    )


@router.get("/school/{school_id}/finance/summary", response_model=FinanceSummary)
def get_school_finance_summary(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    payments = _school_payments(db, context.school_id).all()
    return {
        "total_collected": sum(float(payment.amount_paid or 0) for payment in payments),
        "payments_count": len(payments),
        "today_collections": 0,
    }


@router.get("/school/{school_id}/finance/payments")
def get_school_payments(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return _school_payments(db, context.school_id).all()


@router.get("/school/{school_id}/payroll/summary", response_model=PayrollSummary)
def get_school_payroll_summary(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    payrolls = _school_payrolls(db, context.school_id).all()
    return {
        "total_payroll": sum(float(p.net_salary or 0) for p in payrolls),
        "paid": sum(float(p.amount_paid or 0) for p in payrolls),
        "unpaid": sum(float(p.balance or 0) for p in payrolls),
        "partial": sum(float(p.balance or 0) for p in payrolls if p.status == "partial"),
    }


@router.get("/school/{school_id}/employees")
def get_school_employees(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return db.query(Employee).filter(Employee.school_id == context.school_id).all()


@router.get("/school/{school_id}/payrolls")
def get_school_payrolls(
    school_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _require_requested_school(school_id, context)
    return _school_payrolls(db, context.school_id).all()
