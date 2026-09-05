from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models.tutor_completion import (
    InventoryAsset,
    LibraryBook,
    LibraryLoan,
    SchoolCalendarEvent,
    TransportAssignment,
    TransportRoute,
)
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/operations", tags=["School Operations"])
MANAGERS = ("school_admin", "principal", "vice_principal", "registrar", "librarian", "transport_manager", "asset_manager")


class CalendarCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    category: str = "school"
    starts_at: datetime
    ends_at: datetime | None = None
    audience: str = "all"


class BookCreate(BaseModel):
    isbn: str | None = None
    title: str = Field(min_length=1, max_length=240)
    author: str | None = None
    category: str | None = None
    copies_total: int = Field(default=1, ge=0)


class LoanCreate(BaseModel):
    book_id: UUID
    student_id: UUID
    due_at: datetime


class RouteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    driver_name: str | None = None
    driver_phone: str | None = None
    vehicle_registration: str | None = None
    stops: list[dict] = Field(default_factory=list)


class TransportAssign(BaseModel):
    route_id: UUID
    student_id: UUID
    pickup_stop: str | None = None
    dropoff_stop: str | None = None


class AssetCreate(BaseModel):
    asset_code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = None
    quantity: int = Field(default=1, ge=0)
    location: str | None = None


@router.get("/calendar")
def calendar(db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    return db.query(SchoolCalendarEvent).filter(SchoolCalendarEvent.school_id == context.school_id).order_by(SchoolCalendarEvent.starts_at.asc()).all()


@router.post("/calendar")
def add_calendar_event(payload: CalendarCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*MANAGERS))):
    event = SchoolCalendarEvent(school_id=context.school_id, **payload.model_dump())
    db.add(event); db.commit(); db.refresh(event); return event


@router.get("/library/books")
def books(db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    return db.query(LibraryBook).filter(LibraryBook.school_id == context.school_id).order_by(LibraryBook.title.asc()).all()


@router.post("/library/books")
def add_book(payload: BookCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*MANAGERS))):
    book = LibraryBook(school_id=context.school_id, copies_available=payload.copies_total, **payload.model_dump())
    db.add(book); db.commit(); db.refresh(book); return book


@router.post("/library/loans")
def borrow_book(payload: LoanCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*MANAGERS))):
    book = db.query(LibraryBook).filter(LibraryBook.id == payload.book_id, LibraryBook.school_id == context.school_id).with_for_update().first()
    if not book or book.copies_available <= 0:
        raise HTTPException(status_code=409, detail="book is not available")
    book.copies_available -= 1
    loan = LibraryLoan(
        school_id=context.school_id,
        book_id=payload.book_id,
        student_id=payload.student_id,
        borrowed_at=datetime.now(timezone.utc),
        due_at=payload.due_at,
    )
    db.add(loan); db.commit(); db.refresh(loan); return loan


@router.put("/library/loans/{loan_id}/return")
def return_book(loan_id: UUID, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*MANAGERS))):
    loan = db.query(LibraryLoan).filter(LibraryLoan.id == loan_id, LibraryLoan.school_id == context.school_id).with_for_update().first()
    if not loan:
        raise HTTPException(status_code=404, detail="loan not found")
    if loan.returned_at is None:
        book = db.get(LibraryBook, loan.book_id)
        loan.returned_at = datetime.now(timezone.utc)
        loan.status = "returned"
        if book:
            book.copies_available = min(book.copies_total, book.copies_available + 1)
    db.commit(); db.refresh(loan); return loan


@router.get("/transport/routes")
def routes(db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    return db.query(TransportRoute).filter(TransportRoute.school_id == context.school_id, TransportRoute.is_active.is_(True)).all()


@router.post("/transport/routes")
def add_route(payload: RouteCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*MANAGERS))):
    route = TransportRoute(school_id=context.school_id, **payload.model_dump())
    db.add(route); db.commit(); db.refresh(route); return route


@router.post("/transport/assignments")
def assign_transport(payload: TransportAssign, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*MANAGERS))):
    item = TransportAssignment(school_id=context.school_id, **payload.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item


@router.get("/assets")
def assets(db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    return db.query(InventoryAsset).filter(InventoryAsset.school_id == context.school_id).order_by(InventoryAsset.name.asc()).all()


@router.post("/assets")
def add_asset(payload: AssetCreate, db: Session = Depends(get_db), context: SchoolContext = Depends(require_school_roles(*MANAGERS))):
    asset = InventoryAsset(school_id=context.school_id, **payload.model_dump())
    db.add(asset); db.commit(); db.refresh(asset); return asset
