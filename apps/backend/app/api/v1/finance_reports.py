import csv
from calendar import monthrange
from datetime import date
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_platform_owner
from app.db.session import get_db
from app.models import FinanceClient, FinanceInvoice, User
from app.services.finance_ledger import aging_out, client_out, invoice_financial_out

router = APIRouter(prefix="/finance/reports", tags=["finance-reports"])


def _invoices(db: Session) -> list[FinanceInvoice]:
    return list(db.scalars(
        select(FinanceInvoice)
        .options(
            selectinload(FinanceInvoice.payments),
            selectinload(FinanceInvoice.credit_notes),
            selectinload(FinanceInvoice.items),
        )
        .order_by(FinanceInvoice.created_at.desc())
    ).all())


def _period_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return start, end


def _period_rows(invoices: list[FinanceInvoice], start: date, end: date) -> list[dict]:
    rows: list[dict] = []
    for invoice in invoices:
        if not invoice.created_at:
            continue
        issued = invoice.created_at.date()
        if issued < start or issued > end:
            continue
        rows.append(invoice_financial_out(invoice))
    return rows


@router.get("/aging")
def finance_aging_report(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    return aging_out(_invoices(db))


@router.get("/period")
def finance_period_report(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    start, end = _period_bounds(year, month)
    invoices = _invoices(db)
    rows = _period_rows(invoices, start, end)
    active = [row for row in rows if row["status"] != "cancelled"]
    collected = 0
    for invoice in invoices:
        for payment in invoice.payments:
            if start <= payment.payment_date <= end:
                collected += payment.amount_minor
    return {
        "period": f"{year:04d}-{month:02d}",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "invoice_count": len(active),
        "gross_invoiced_minor": sum(row["total_minor"] for row in active),
        "credits_minor": sum(row.get("credited_minor", 0) for row in active),
        "net_invoiced_minor": sum(row.get("adjusted_total_minor", row["total_minor"]) for row in active),
        "collected_minor": collected,
        "outstanding_minor": sum(row["outstanding_minor"] for row in active),
        "items": rows,
    }


@router.get("/trend")
def finance_trend_report(
    months: int = Query(default=12, ge=3, le=24),
    db: Session = Depends(get_db),
    current: User = Depends(require_platform_owner),
):
    del current
    today = date.today()
    invoices = _invoices(db)
    periods: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(months):
        periods.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    periods.reverse()
    result = []
    for year, month in periods:
        start, end = _period_bounds(year, month)
        rows = _period_rows(invoices, start, end)
        active = [row for row in rows if row["status"] != "cancelled"]
        collected = sum(
            payment.amount_minor
            for invoice in invoices
            for payment in invoice.payments
            if start <= payment.payment_date <= end
        )
        result.append({
            "period": f"{year:04d}-{month:02d}",
            "label": start.strftime("%b %Y"),
            "invoiced_minor": sum(row.get("adjusted_total_minor", row["total_minor"]) for row in active),
            "collected_minor": collected,
            "outstanding_minor": sum(row["outstanding_minor"] for row in active),
            "invoice_count": len(active),
        })
    return {"months": result}


@router.get("/clients/{client_id}/statement")
def finance_client_statement(client_id: UUID, db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    client = db.get(FinanceClient, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Finance client not found")
    invoices = list(db.scalars(
        select(FinanceInvoice)
        .options(
            selectinload(FinanceInvoice.payments),
            selectinload(FinanceInvoice.credit_notes),
            selectinload(FinanceInvoice.items),
        )
        .where(FinanceInvoice.client_id == client.id)
        .order_by(FinanceInvoice.created_at.asc())
    ).all())
    rows = [invoice_financial_out(invoice) for invoice in invoices]
    active = [item for item in rows if item["status"] != "cancelled"]
    return {
        "client": client_out(client),
        "items": rows,
        "total_invoiced_minor": sum(item["total_minor"] for item in active),
        "total_credited_minor": sum(item.get("credited_minor", 0) for item in active),
        "net_invoiced_minor": sum(item.get("adjusted_total_minor", item["total_minor"]) for item in active),
        "total_paid_minor": sum(item["paid_minor"] for item in active),
        "balance_minor": sum(item["outstanding_minor"] for item in active),
    }


@router.get("/invoices.csv")
def export_finance_invoices_csv(db: Session = Depends(get_db), current: User = Depends(require_platform_owner)):
    del current
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Invoice", "Client", "Recipient", "Description", "Original Total (LSL)", "Credits (LSL)", "Net Total (LSL)", "Paid (LSL)", "Outstanding (LSL)", "Due Date", "Status"])
    for invoice in _invoices(db):
        item = invoice_financial_out(invoice)
        writer.writerow([
            item["invoice_number"], item["client_name"], item["recipient_email"], item["description"],
            f'{item["total_minor"] / 100:.2f}', f'{item.get("credited_minor", 0) / 100:.2f}',
            f'{item.get("adjusted_total_minor", item["total_minor"]) / 100:.2f}', f'{item["paid_minor"] / 100:.2f}',
            f'{item["outstanding_minor"] / 100:.2f}', item["due_date"], item["status"],
        ])
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="ithute-finance-invoices.csv"'},
    )
