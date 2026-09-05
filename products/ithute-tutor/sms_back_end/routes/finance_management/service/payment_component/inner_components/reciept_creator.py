from datetime import datetime

from routes.finance_management.service.payment_component.inner_components.other.build_receipt_path import \
    build_receipt_path
from routes.finance_management.service.payment_component.inner_components.other.generate_reciept_pdf import \
    generate_receipt_pdf
from routes.finance_management.service.payment_component.inner_components.other.next_receipt import \
    get_next_receipt_count


def build_payment_receipt_pdf(
        student,
        payment,
        allocation_results,
        remaining_credit,
        total_balance
):

    # =====================================================
    # CURRENT ACADEMIC YEAR (AUTO)
    # =====================================================
    academic_year = str(datetime.now().year)

    # =====================================================
    # AUTO RECEIPT NUMBER BASED ON DIRECTORY
    # =====================================================
    receipt_count = get_next_receipt_count(
        student,
        academic_year
    )

    # =====================================================
    # BUILD PATH
    # =====================================================
    file_path = build_receipt_path(
        student,
        academic_year,
        receipt_count
    )

    # =====================================================
    # GENERATE PDF
    # =====================================================
    pdf_path = generate_receipt_pdf(
        file_path=file_path,
        student=student,
        payment=payment,
        allocation_results=allocation_results,
        remaining_credit=remaining_credit,
        total_balance=total_balance
    )

    return {
        "receipt_number": f"RCT-{payment.id}",
        "receipt_file": pdf_path,
        "academic_year": academic_year,
        "receipt_sequence": receipt_count
    }