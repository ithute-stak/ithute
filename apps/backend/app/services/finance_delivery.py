from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import FinanceDeliveryEvent, FinanceInvoice
from app.services.finance_audit import log_finance_action
from app.services.finance_governance import ensure_invoice_approved_for_send
from app.services.finance_invoice_multi import render_invoice_pdf
from app.services.finance_invoices import build_email_html
from app.services.finance_mail import send_finance_message


def send_invoice(db: Session, invoice: FinanceInvoice) -> None:
    ensure_invoice_approved_for_send(db, invoice)
    pdf = render_invoice_pdf(invoice)
    try:
        result = send_finance_message(
            db,
            recipient=invoice.recipient_email,
            subject=invoice.email_subject,
            text_body=invoice.email_body,
            html_body=build_email_html(invoice),
            attachment_filename=f"{invoice.invoice_number}.pdf",
            attachment_data=pdf,
        )
        now = datetime.now(timezone.utc)
        invoice.status = "sent"
        invoice.sent_at = now
        invoice.last_error = None
        db.add(FinanceDeliveryEvent(
            invoice_id=invoice.id,
            event_type="accepted",
            source="finance_smtp",
            provider_message_id=str(result.get("provider_message_id") or ""),
            detail="SMTP server accepted the outbound message for delivery",
            occurred_at=now,
        ))
        log_finance_action(
            db,
            action="finance.invoice.sent",
            resource_type="finance_invoice",
            resource_id=invoice.id,
            metadata={
                "invoice_number": invoice.invoice_number,
                "recipient": invoice.recipient_email,
                "delivery_state": "accepted",
                "provider_message_id": result.get("provider_message_id"),
            },
        )
    except Exception as exc:
        now = datetime.now(timezone.utc)
        invoice.status = "failed"
        invoice.last_error = str(exc)[:2000]
        db.add(FinanceDeliveryEvent(
            invoice_id=invoice.id,
            event_type="failed",
            source="finance_smtp",
            provider_message_id="",
            detail=str(exc)[:2000],
            occurred_at=now,
        ))
        log_finance_action(
            db,
            action="finance.invoice.send_failed",
            resource_type="finance_invoice",
            resource_id=invoice.id,
            metadata={"invoice_number": invoice.invoice_number, "recipient": invoice.recipient_email, "error": str(exc)[:500]},
        )
        raise
