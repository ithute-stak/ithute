from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, joinedload

from database.multi_tenant_school_management.models import (
    EmployeePayroll,
    EmployeePayment,
    EmployeePaymentAllocation,
    EmployeeCredit,
)


def generate_employee_payment_number(db: Session):
    year = datetime.now().year
    prefix = f"EMP-PAY-{year}-"

    last_payment = (
        db.query(EmployeePayment)
        .filter(EmployeePayment.payment_number.like(f"{prefix}%"))
        .order_by(EmployeePayment.payment_number.desc())
        .first()
    )

    if not last_payment:
        next_number = 1
    else:
        last_sequence = int(
            last_payment.payment_number.replace(prefix, "")
        )
        next_number = last_sequence + 1

    return f"{prefix}{next_number:06d}"


class EmployeePaymentService:

    @staticmethod
    def pay_employee(
        db: Session,
        employee_id,
        amount_paid,
        payment_method: str,
        reference: str | None = None,
    ):
        remaining_amount = Decimal(str(amount_paid))

        payment = EmployeePayment(
            employee_id=employee_id,
            amount_paid=remaining_amount,
            payment_method=payment_method,
            reference=reference,
            payment_number=generate_employee_payment_number(db),
        )

        db.add(payment)
        db.flush()

        payrolls = (
            db.query(EmployeePayroll)
            .filter(
                EmployeePayroll.employee_id == employee_id,
                EmployeePayroll.status.in_(["unpaid", "partial"]),
            )
            .order_by(
                EmployeePayroll.payroll_year.asc(),
                EmployeePayroll.created_at.asc(),
            )
            .all()
        )

        allocations = []

        for payroll in payrolls:
            if remaining_amount <= 0:
                break

            payroll_balance = payroll.balance or Decimal("0")

            if payroll_balance <= 0:
                continue

            allocated = min(remaining_amount, payroll_balance)

            allocation = EmployeePaymentAllocation(
                payment_id=payment.id,
                payroll_id=payroll.id,
                amount_allocated=allocated,
            )

            db.add(allocation)

            payroll.amount_paid = (
                payroll.amount_paid or Decimal("0")
            ) + allocated

            payroll.balance = payroll_balance - allocated

            if payroll.balance <= 0:
                payroll.status = "paid"
                payroll.balance = Decimal("0")
            elif payroll.amount_paid > 0:
                payroll.status = "partial"
            else:
                payroll.status = "unpaid"

            remaining_amount -= allocated
            allocations.append(allocation)

        credit_created = False
        credit = None

        if remaining_amount > 0:
            credit = EmployeeCredit(
                employee_id=employee_id,
                amount=remaining_amount,
                source_payment_id=payment.id,
            )

            db.add(credit)
            credit_created = True

        db.commit()
        db.refresh(payment)

        return {
            "message": "Employee payment processed successfully",
            "payment": payment,
            "remaining_credit": remaining_amount,
            "credit_created": credit_created,
            "credit": credit,
        }

    @staticmethod
    def get_all_payments(db: Session):
        return (
            db.query(EmployeePayment)
            .options(
                joinedload(EmployeePayment.allocations),
                joinedload(EmployeePayment.employee),
            )
            .order_by(EmployeePayment.created_at.desc())
            .all()
        )

    @staticmethod
    def get_employee_payments(db: Session, employee_id):
        return (
            db.query(EmployeePayment)
            .options(
                joinedload(EmployeePayment.allocations),
                joinedload(EmployeePayment.employee),
            )
            .filter(EmployeePayment.employee_id == employee_id)
            .order_by(EmployeePayment.created_at.desc())
            .all()
        )

    @staticmethod
    def get_payment(db: Session, payment_id):
        return (
            db.query(EmployeePayment)
            .options(
                joinedload(EmployeePayment.allocations),
                joinedload(EmployeePayment.employee),
            )
            .filter(EmployeePayment.id == payment_id)
            .first()
        )