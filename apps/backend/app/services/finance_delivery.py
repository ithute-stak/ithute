from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import FinanceInvoice
from app.services.finance_audit import log_finance_action
from app.services.finance_invoice_multi import render_invoice_pdf
from app.services.finance_invoices import build_email_html
from app.services.finance_mail import send_finance_message


def send_invoice(db: Session, invoice: FinanceInvoice) -> None:
    pdf = render_invoice_pdf(invoice)
    try:
        send_finance_message(
            db,
            recipient=invoice.recipient_email,
            subject=invoice.email_subject,
            text_body=invoice.email_body,
            html_body=build_email_html(invoice),
            attachment_filename=f"{invoice.invoice_number}.pdf",
            attachment_data=pdf,
        )
        invoice.status = "sent"
        invoice.sent_at = datetime.now(timezone.utc)
        invoice.last_error = None
        log_finance_action(
            db,
            action="finance.invoice.sent",
            resource_type="finance_invoice",
            resource_id=invoice.id,
            metadata={"invoice_number": invoice.invoice_number, "recipient": invoice.recipient_email},
        )
    except Exception as exc:
        invoice.status = "failed"
        invoice.last_error = str(exc)[:2000]
        log_finance_action(
            db,
            action="finance.invoice.send_failed",
            resource_type="finance_invoice",
            resource_id=invoice.id,
            metadata={"invoice_number": invoice.invoice_number, "recipient": invoice.recipient_email, "error": str(exc)[:500]},
        )
        raise
