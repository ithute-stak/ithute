from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database.employee_management.model.empliyee_payrol import EmployeePayroll
from database.employee_management.model.employee import Employee
from database.finace_management.models.feeInvoice import FeeInvoice
from database.finace_management.models.studentFeePayment import FeePayment
from database.multi_tenant_school_management.models import StudentAttendance, StudentEnrollment, Teacher
from database.multi_tenant_school_management.models.academic_core import AcademicTerm, AcademicYear, Assessment, AssessmentResult
from database.session import get_db
from utils.school_context import SchoolContext, require_school_roles

router = APIRouter(prefix="/reports", tags=["School Reports"])

REPORT_ROLES = ("school_admin", "principal", "vice_principal", "bursar", "accountant")


def _money(value) -> float:
    return round(float(value or 0), 2)


@router.get("/overview")
def school_management_overview(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*REPORT_ROLES)),
):
    school_id = context.school_id

    active_students = db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == school_id,
        StudentEnrollment.is_current.is_(True),
    ).count()
    teachers = db.query(Teacher).filter(Teacher.school_id == school_id).count()
    employees = db.query(Employee).filter(Employee.school_id == school_id).count()

    attendance_total = db.query(StudentAttendance).filter(StudentAttendance.school_id == school_id).count()
    attendance_present = db.query(StudentAttendance).filter(
        StudentAttendance.school_id == school_id,
        StudentAttendance.status.in_(["present", "late"]),
    ).count()
    attendance_absent = db.query(StudentAttendance).filter(
        StudentAttendance.school_id == school_id,
        StudentAttendance.status == "absent",
    ).count()
    attendance_rate = round(attendance_present / attendance_total * 100, 2) if attendance_total else None

    invoices = db.query(
        func.coalesce(func.sum(FeeInvoice.amount_due), 0),
        func.coalesce(func.sum(FeeInvoice.amount_paid), 0),
        func.coalesce(func.sum(FeeInvoice.balance), 0),
        func.count(FeeInvoice.id),
    ).filter(FeeInvoice.school_id == school_id).one()
    payment_total = db.query(func.coalesce(func.sum(FeePayment.amount_paid), 0)).filter(
        FeePayment.school_id == school_id
    ).scalar()
    overdue_count = db.query(FeeInvoice).filter(
        FeeInvoice.school_id == school_id,
        FeeInvoice.balance > 0,
        FeeInvoice.due_date.is_not(None),
        FeeInvoice.due_date < date.today(),
    ).count()

    payroll = db.query(
        func.coalesce(func.sum(EmployeePayroll.net_salary), 0),
        func.coalesce(func.sum(EmployeePayroll.amount_paid), 0),
        func.coalesce(func.sum(EmployeePayroll.balance), 0),
    ).join(Employee, Employee.id == EmployeePayroll.employee_id).filter(
        Employee.school_id == school_id
    ).one()

    current_year = db.query(AcademicYear).filter(
        AcademicYear.school_id == school_id,
        AcademicYear.is_current.is_(True),
    ).first()
    current_term = db.query(AcademicTerm).filter(
        AcademicTerm.school_id == school_id,
        AcademicTerm.is_current.is_(True),
    ).first()
    assessments = db.query(Assessment).filter(Assessment.school_id == school_id).count()
    published_assessments = db.query(Assessment).filter(
        Assessment.school_id == school_id,
        Assessment.is_published.is_(True),
    ).count()

    result_average = db.query(
        func.avg((AssessmentResult.score / Assessment.max_score) * 100)
    ).join(Assessment, Assessment.id == AssessmentResult.assessment_id).filter(
        AssessmentResult.school_id == school_id,
        Assessment.is_published.is_(True),
        AssessmentResult.score.is_not(None),
        Assessment.max_score > 0,
        AssessmentResult.is_absent.is_(False),
    ).scalar()

    return {
        "school_id": str(school_id),
        "generated_on": date.today().isoformat(),
        "people": {
            "active_students": active_students,
            "teachers": teachers,
            "employees": employees,
        },
        "academics": {
            "current_year": current_year.name if current_year else None,
            "current_term": current_term.name if current_term else None,
            "assessments": assessments,
            "published_assessments": published_assessments,
            "average_published_score_percent": round(float(result_average), 2) if result_average is not None else None,
        },
        "attendance": {
            "records": attendance_total,
            "present_or_late": attendance_present,
            "absent": attendance_absent,
            "attendance_rate_percent": attendance_rate,
        },
        "finance": {
            "invoices_count": int(invoices[3] or 0),
            "amount_invoiced": _money(invoices[0]),
            "amount_allocated_paid": _money(invoices[1]),
            "outstanding_balance": _money(invoices[2]),
            "cash_received": _money(payment_total),
            "overdue_invoices": overdue_count,
        },
        "payroll": {
            "net_payroll": _money(payroll[0]),
            "amount_paid": _money(payroll[1]),
            "outstanding_balance": _money(payroll[2]),
        },
    }


@router.get("/attendance/trend")
def attendance_trend(
    days: int = 30,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*REPORT_ROLES)),
):
    days = max(1, min(days, 366))
    start = date.today() - timedelta(days=days - 1)
    rows = db.query(
        StudentAttendance.attendance_date,
        func.count(StudentAttendance.id),
        func.sum(case((StudentAttendance.status.in_(["present", "late"]), 1), else_=0)),
    ).filter(
        StudentAttendance.school_id == context.school_id,
        StudentAttendance.attendance_date >= start,
    ).group_by(StudentAttendance.attendance_date).order_by(StudentAttendance.attendance_date.asc()).all()

    return [
        {
            "date": day.isoformat(),
            "records": int(total or 0),
            "present_or_late": int(present or 0),
            "rate_percent": round((present or 0) / total * 100, 2) if total else None,
        }
        for day, total, present in rows
    ]
