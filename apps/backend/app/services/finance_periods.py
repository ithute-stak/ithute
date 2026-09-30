from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
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
