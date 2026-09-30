from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.finance_control import FinanceAccountingPeriod


def period_key(value: date) -> tuple[int, int]:
    return value.year, value.month


def get_period(db: Session, value: date) -> FinanceAccountingPeriod | None:
    year, month = period_key(value)
    return db.scalar(
        select(FinanceAccountingPeriod).where(
            FinanceAccountingPeriod.year == year,
            FinanceAccountingPeriod.month == month,
        )
    )


def period_is_locked(db: Session, value: date) -> bool:
    row = get_period(db, value)
    return bool(row and row.status == "locked")


def ensure_period_open(db: Session, value: date, *, operation: str) -> None:
    if period_is_locked(db, value):
        raise ValueError(
            f"Accounting period {value.year:04d}-{value.month:02d} is locked; {operation} is not allowed"
        )


def period_out(row: FinanceAccountingPeriod) -> dict:
    return {
        "id": str(row.id),
        "year": row.year,
        "month": row.month,
        "period": f"{row.year:04d}-{row.month:02d}",
        "status": row.status,
        "note": row.note,
        "locked_at": row.locked_at.isoformat() if row.locked_at else None,
        "locked_by_user_id": str(row.locked_by_user_id) if row.locked_by_user_id else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def lock_period(row: FinanceAccountingPeriod, *, user_id, note: str = "") -> None:
    row.status = "locked"
    row.note = note.strip()
    row.locked_at = datetime.now(timezone.utc)
    row.locked_by_user_id = user_id


def reopen_period(row: FinanceAccountingPeriod, *, note: str = "") -> None:
    row.status = "open"
    row.note = note.strip()
    row.locked_at = None
    row.locked_by_user_id = None


def _accounting_date(obj) -> date | None:
    from app.models.finance import FinanceCreditNote, FinanceInvoice, FinancePayment
    from app.models.finance_accounting import FinanceBankTransaction, FinanceExpense
    from app.models.finance_control import FinanceRefund

    if isinstance(obj, FinancePayment):
        return obj.payment_date
    if isinstance(obj, FinanceExpense):
        return obj.expense_date
    if isinstance(obj, FinanceBankTransaction):
        return obj.transaction_date
    if isinstance(obj, FinanceRefund):
        return obj.refund_date
    if isinstance(obj, FinanceInvoice):
        return obj.created_at.date() if obj.created_at else date.today()
    if isinstance(obj, FinanceCreditNote):
        return obj.created_at.date() if obj.created_at else date.today()
    return None


@event.listens_for(Session, "before_flush")
def _guard_locked_finance_periods(session: Session, flush_context, instances) -> None:
    del flush_context, instances
    candidates = list(session.new) + list(session.dirty) + list(session.deleted)
    checked: set[tuple[int, int]] = set()
    for obj in candidates:
        if isinstance(obj, FinanceAccountingPeriod):
            continue
        value = _accounting_date(obj)
        if value is None:
            continue
        key = (value.year, value.month)
        if key in checked:
            continue
        checked.add(key)
        locked = session.scalar(
            select(FinanceAccountingPeriod.id).where(
                FinanceAccountingPeriod.year == value.year,
                FinanceAccountingPeriod.month == value.month,
                FinanceAccountingPeriod.status == "locked",
            ).limit(1)
        )
        if locked is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Accounting period {value.year:04d}-{value.month:02d} is locked; financial records in that period are read-only",
            )
