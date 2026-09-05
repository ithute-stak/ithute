from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from database.base import Base


class StaffLeaveRequest(Base):
    __tablename__ = "staff_leave_requests"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_type = Column(String(60), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(24), nullable=False, default="pending", index=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_staff_leave_dates"),
        CheckConstraint("status IN ('pending','approved','rejected','cancelled')", name="ck_staff_leave_status"),
    )


class Supplier(Base):
    __tablename__ = "suppliers"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(80), nullable=True)
    address = Column(Text, nullable=True)
    tax_number = Column(String(100), nullable=True)
    status = Column(String(24), nullable=False, default="active")

    __table_args__ = (
        UniqueConstraint("school_id", "name", name="uq_supplier_school_name"),
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    order_number = Column(String(80), nullable=False)
    items = Column(JSON, nullable=False, default=list)
    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    status = Column(String(24), nullable=False, default="draft", index=True)
    ordered_on = Column(Date, nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    __table_args__ = (
        UniqueConstraint("school_id", "order_number", name="uq_purchase_order_number"),
        CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total_amount >= 0", name="ck_purchase_order_amounts"),
    )


class SchoolExpense(Base):
    __tablename__ = "school_expenses"

    school_id = Column(UUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    purchase_order_id = Column(UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    expense_date = Column(Date, nullable=False)
    reference = Column(String(120), nullable=True)
    status = Column(String(24), nullable=False, default="recorded")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_school_expense_amount"),
    )
