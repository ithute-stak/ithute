from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy.orm import Session

from database.finace_management.models.fee_payment_allocation import FeePaymentAllocation
from database.multi_tenant_school_management.models import (
    Student,
    Class,
    Grade,
    FeePlan,
    FeeInvoice,
    FeePayment,
    StudentCredit,
    SchoolFeeConfiguration
)
from database.multi_tenant_school_management.schemas.notification import NotificationRead
from routes.finance_management.service.payment_component.create_quarterly_payment import create_student_quarter_invoices
from routes.finance_management.service.payment_component.generate_payment_number import generate_receipt_number
from routes.finance_management.service.payment_component.inner_components.reciept_creator import \
    build_payment_receipt_pdf
from sqlalchemy.exc import IntegrityError

from routes.service.notifications import create_notification
from ws.broadcasting.stundent_payment import student_payment_socket


async def create_student_payment_nit(db: Session, payLoad):
    # =====================================================
    # 1. GET STUDENT
    # =====================================================
    student = db.get(Student, payLoad.student_id)

    if not student:
        raise HTTPException(404, "Student not found")

    # =====================================================
    # 2. CONFIG
    # =====================================================
    fee_config = (
        db.query(SchoolFeeConfiguration)
        .filter(SchoolFeeConfiguration.school_id == student.user.school_id)
        .first()
    )

    if not fee_config:
        raise HTTPException(404, "Fee config not found")

    # =====================================================
    # 3. CLASS + GRADE + PLAN
    # =====================================================
    student_class = db.query(Class).filter(Class.id == student.class_id).first()
    student_grade = db.query(Grade).filter(Grade.id == student_class.grade_id).first()

    fee_plan = (
        db.query(FeePlan)
        .filter(
            FeePlan.feeConfig_id == fee_config.id,
            FeePlan.grade_id == student_grade.id
        )
        .first()
    )

    if not fee_plan:
        raise HTTPException(404, "Fee plan not found")

    # =====================================================
    # 4. ENSURE INVOICES EXIST
    # =====================================================
    create_student_quarter_invoices(
        db=db,
        student=student,
        fee_plan=fee_plan,
        fee_config=fee_config
    )

    # =====================================================
    # 5. PAYMENT AMOUNT
    # =====================================================
    payment_amount = Decimal(str(payLoad.amount_paid)).quantize(Decimal("0.01"))

    if payment_amount <= 0:
        raise HTTPException(400, "Invalid payment amount")

    # =====================================================
    # 6. CREATE PAYMENT RECORD
    # =====================================================
    payment = FeePayment(
        student_id=student.id,
        amount_paid=payment_amount,
        payment_method=payLoad.payment_method or "cash",
        reference=payLoad.reference or "manual",
        payment_number=generate_receipt_number(db)
    )

    for _ in range(5):
        payment.payment_number = generate_receipt_number(db)

        try:
            db.add(payment)
            db.flush()
            break
        except IntegrityError:
            db.rollback()
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate unique payment number",
        )

    # =====================================================
    # 7. GET UNPAID INVOICES
    # =====================================================
    invoices = (
        db.query(FeeInvoice)
        .filter(
            FeeInvoice.student_id == student.id,
            FeeInvoice.fee_plan_id == fee_plan.id,
            FeeInvoice.balance > 0
        )
        .order_by(FeeInvoice.period_start.asc())
        .all()
    )

    allocation_results = []
    # =====================================================
    # STEP 1: APPLY EXISTING CREDITS TO INVOICES
    # =====================================================
    credit_rows = (
        db.query(StudentCredit)
        .filter(
            StudentCredit.student_id == student.id,
            StudentCredit.amount > 0
        )
        .order_by(StudentCredit.created_at.asc())
        .all()
    )

    for invoice in invoices:

        if invoice.balance <= 0:
            continue

        invoice_balance = Decimal(str(invoice.balance))

        for credit in credit_rows:

            if credit.amount <= 0:
                continue

            apply_amount = min(
                Decimal(str(credit.amount)),
                invoice_balance
            )

            # APPLY CREDIT TO INVOICE
            invoice.amount_paid = (
                    Decimal(str(invoice.amount_paid))
                    + apply_amount
            )

            invoice.balance = (
                    invoice_balance
                    - apply_amount
            )

            invoice.status = (
                "paid"
                if invoice.balance == 0
                else "partial"
            )

            # REDUCE CREDIT
            credit.amount = (
                    Decimal(str(credit.amount))
                    - apply_amount
            )

            invoice_balance = Decimal(str(invoice.balance))

            db.add(invoice)
            db.add(credit)

            allocation_results.append({
                "type": "credit",
                "quarter": invoice.quarter,
                "allocated": str(apply_amount),
                "balance": str(invoice.balance),
                "status": invoice.status
            })

            if invoice.balance == 0:
                break

    # =====================================================
    # STEP 2: APPLY CASH PAYMENT
    # =====================================================
    remaining_payment = payment_amount

    for invoice in invoices:

        if remaining_payment <= 0:
            break

        balance = Decimal(str(invoice.balance))

        if balance <= 0:
            continue

        allocated = min(balance, remaining_payment)

        # -----------------------------
        # UPDATE INVOICE
        # -----------------------------
        invoice.amount_paid = (
                Decimal(str(invoice.amount_paid))
                + allocated
        )

        invoice.balance = balance - allocated

        invoice.status = (
            "paid"
            if invoice.balance == 0
            else "partial"
        )

        db.add(invoice)

        # -----------------------------
        # CREATE ALLOCATION RECORD
        # -----------------------------
        allocation = FeePaymentAllocation(
            payment_id=payment.id,
            invoice_id=invoice.id,
            amount_allocated=allocated
        )

        db.add(allocation)

        # -----------------------------
        # RESPONSE DATA
        # -----------------------------
        allocation_results.append({
            "type": "cash",
            "invoice": invoice.invoice_number,
            "quarter": invoice.quarter,
            "allocated": str(allocated),
            "balance": str(invoice.balance),
            "status": invoice.status
        })

        remaining_payment -= allocated

    # =====================================================
    # 9. CREATE CREDIT (DYNAMIC)
    # =====================================================
    remaining_payment = remaining_payment.quantize(
        Decimal("0.01")
    )

    if remaining_payment > 0:
        new_credit = StudentCredit(
            student_id=student.id,
            source_payment_id=payment.id,
            amount=remaining_payment,
            academic_year=f"{fee_config.year_start.year}/{fee_config.year_end.year}"
        )

        db.add(new_credit)
    # =====================================================
    # 10. COMMIT
    # =====================================================
    db.commit()
    db.refresh(payment)

    total_allocated = sum(
        Decimal(a["allocated"])
        for a in allocation_results
    )

    total_balance = sum(
        Decimal(str(inv.balance))
        for inv in invoices
    )

    fully_paid_count = len([
        a for a in allocation_results
        if a["status"] == "paid"
    ])

    partial_count = len([
        a for a in allocation_results
        if a["status"] == "partial"
    ])

    # =====================================================
    # 16. BUILD RECEIPT
    # =====================================================
    receipt = build_payment_receipt_pdf(
        student=student,
        payment=payment,
        allocation_results=allocation_results,
        remaining_credit=remaining_payment,
        total_balance=total_balance
    )

    # =====================================================
    # 11. RESPONSE
    # =====================================================
    response = {
            "message": "Payment processed successfully",

            # =========================
            # PAYMENT SUMMARY
            # =========================
            "payment": {
                "payment_id": str(payment.id),
                "student_id": str(student.id),
                "amount_paid": str(payment_amount),
                "payment_method": payment.payment_method,
                "reference": payment.reference,
                "created_at": payment.created_at.isoformat() if payment.created_at else None
            },

            # =========================
            # ALLOCATION SUMMARY
            # =========================
            "allocation_summary": {
                "total_allocated": str(
                    sum(Decimal(a["allocated"]) for a in allocation_results)
                ),
                "total_invoices_affected": len(allocation_results),
                "fully_paid_invoices": len([
                    a for a in allocation_results if a["status"] == "paid"
                ]),
                "partially_paid_invoices": len([
                    a for a in allocation_results if a["status"] == "partial"
                ])
            },

            # =========================
            # DETAILED ALLOCATIONS
            # =========================
            "allocations": allocation_results,

            # =========================
            # CREDIT INFO
            # =========================
            "credit": {
                "remaining_credit": str(remaining_payment),
                "credit_created": remaining_payment > 0
            },

            # =========================
            # STUDENT FINANCIAL SNAPSHOT
            # =========================
            "student_snapshot": {
                "student_id": str(student.id),
                "total_outstanding_after_payment": str(
                    sum(
                        Decimal(str(inv.balance))
                        for inv in invoices
                    )
                ),
                "status": (
                    "fully_paid"
                    if sum(Decimal(str(inv.balance)) for inv in invoices) == 0
                    else "partial"
                )
            },
            # RECEIPT
            "receipt": receipt
        }

    notification = create_notification(
        db=db,
        channel='finance',
        title="Payment Received",
        message=f"M{float(str(payment_amount)):.2f} payment received. Paying for Student: {student.admission_number}.",
        event="PAYMENT_COMPLETED",
    )

    notification_data = NotificationRead.model_validate(
        notification
    ).model_dump()

    await student_payment_socket(
        notification = notification_data,
        data= response
    )

    return response
