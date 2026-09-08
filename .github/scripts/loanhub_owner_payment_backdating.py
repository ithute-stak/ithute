from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("products/LoanHub")
BACKEND = ROOT / "apps/backend"
FRONTEND = ROOT / "apps/frontend"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, got {count}")
    path.write_text(text.replace(old, new, 1))


def regex_once(path: Path, pattern: str, replacement: str, label: str) -> None:
    text = path.read_text()
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, got {count}")
    path.write_text(updated)


# Central policy: the business/effective date may be earlier only for Company Owner.
policy = BACKEND / "utils/payment_dates.py"
policy.write_text('''from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from database.models.enums import UserRole

LESOTHO_TIMEZONE = ZoneInfo("Africa/Maseru")


def lesotho_today() -> date:
    return datetime.now(LESOTHO_TIMEZONE).date()


def resolve_effective_payment_date(
    role: UserRole | None,
    requested_date: date | None,
    *,
    today: date | None = None,
) -> date:
    current_date = today or lesotho_today()
    effective_date = requested_date or current_date
    if effective_date > current_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment date cannot be in the future.",
        )
    if effective_date < current_date and role != UserRole.COMPANY_OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the Company Owner can record a backdated payment.",
        )
    return effective_date


def assert_manual_backdate(payment_method: object, effective_date: date, *, today: date | None = None) -> None:
    current_date = today or lesotho_today()
    method_value = getattr(payment_method, "value", str(payment_method))
    if effective_date < current_date and method_value != "cash":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Backdating is available only for manually recorded cash payments; provider-settled payments keep their actual provider date.",
        )
''')

# Payment ledger gets a business date independent of immutable audit timestamps.
model = BACKEND / "database/models/payment.py"
replace_once(model, "from sqlalchemy import Column, DateTime, Enum, ForeignKey, Numeric, String, Text\n", "from datetime import date\n\nfrom sqlalchemy import Column, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, text\n", "payment model imports")
replace_once(model, "    amount = Column(Numeric(15, 2), nullable=False)\n    currency = Column(String(3), nullable=False, default=\"LSL\")\n", "    amount = Column(Numeric(15, 2), nullable=False)\n    effective_date = Column(Date, nullable=False, default=date.today, server_default=text(\"CURRENT_DATE\"), index=True)\n    currency = Column(String(3), nullable=False, default=\"LSL\")\n", "payment effective date column")

schema = BACKEND / "database/schemas/payment.py"
replace_once(schema, "from datetime import datetime\n", "from datetime import date, datetime\n", "payment schema date import")
replace_once(schema, "    amount: Decimal\n    currency: str\n", "    amount: Decimal\n    effective_date: date\n    currency: str\n", "payment schema effective date")

cash_schema = BACKEND / "database/schemas/cash.py"
replace_once(cash_schema, "class CashRepaymentCreate(CashRepaymentPreviewCreate):\n", "class CashRepaymentCreate(CashRepaymentPreviewCreate):\n    payment_date: date | None = None\n", "cash repayment date field")
replace_once(cash_schema, "class InstallmentPaymentCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n", "class InstallmentPaymentCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n    payment_date: date | None = None\n", "installment payment date field")

early_schema = BACKEND / "database/schemas/early_settlement.py"
replace_once(early_schema, "class EarlySettlementPayCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n", "class EarlySettlementPayCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n    payment_date: date | None = None\n", "early settlement date field")

client_schema = BACKEND / "database/schemas/company_clients.py"
replace_once(client_schema, "class CashOpeningFeeSettlementCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n", "class CashOpeningFeeSettlementCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n    payment_date: date | None = None\n", "opening fee date field")

# Core repayment service persists effective date while leaving verified/completed/created timestamps at actual entry time.
loan_service = BACKEND / "services/loan_service.py"
replace_once(loan_service, "    notes: str | None = None,\n    idempotency_key: str | None = None,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    \"\"\"Post a loan repayment through cash or a manually verified channel.\"\"\"\n", "    notes: str | None = None,\n    idempotency_key: str | None = None,\n    effective_date: date | None = None,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    \"\"\"Post a loan repayment through cash or a manually verified channel.\"\"\"\n    business_date = effective_date or date.today()\n", "record repayment signature")
replace_once(loan_service, "        amount=preview[\"amount_applied\"],\n        currency=\"LSL\",\n", "        amount=preview[\"amount_applied\"],\n        effective_date=business_date,\n        currency=\"LSL\",\n", "repayment transaction effective date")
replace_once(loan_service, "            \"notes\": notes,\n        },\n", "            \"notes\": notes,\n            \"effective_date\": business_date.isoformat(),\n            \"backdated\": business_date < date.today(),\n        },\n", "repayment provider payload date")
# Installment path delegates to the same posting service.
replace_once(loan_service, "    notes: str | None = None,\n    idempotency_key: str | None = None,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    \"\"\"Record a payment against the current installment only.\n", "    notes: str | None = None,\n    idempotency_key: str | None = None,\n    effective_date: date | None = None,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    \"\"\"Record a payment against the current installment only.\n", "installment signature")
replace_once(loan_service, "        notes=notes,\n        idempotency_key=idempotency_key,\n    )\n\n\ndef allocate_repayment", "        notes=notes,\n        idempotency_key=idempotency_key,\n        effective_date=effective_date,\n    )\n\n\ndef allocate_repayment", "installment delegate date")

# Generic local cash payment service, used by opening-fee settlement.
payment_service = BACKEND / "services/payment_service.py"
replace_once(payment_service, "from datetime import datetime, timezone\n", "from datetime import date, datetime, timezone\n", "payment service date import")
replace_once(payment_service, "    branch_id: UUID | None = None,\n    **_: Any,\n", "    branch_id: UUID | None = None,\n    effective_date: date | None = None,\n    **_: Any,\n", "initiate payment effective param")
replace_once(payment_service, "        amount=value,\n        currency=\"LSL\",\n", "        amount=value,\n        effective_date=effective_date or date.today(),\n        currency=\"LSL\",\n", "generic transaction effective date")

# Early settlement cash posting.
early_service = BACKEND / "services/early_settlement_service.py"
replace_once(early_service, "    gateway_provider: str | None = None,\n    gateway_customer_phone: str | None = None,\n) -> PaymentTransaction:\n", "    gateway_provider: str | None = None,\n    gateway_customer_phone: str | None = None,\n    effective_date: date | None = None,\n) -> PaymentTransaction:\n", "early settlement signature")
replace_once(early_service, "        amount=money(quote.settlement_amount),\n        currency=\"LSL\",\n", "        amount=money(quote.settlement_amount),\n        effective_date=effective_date or date.today(),\n        currency=\"LSL\",\n", "early settlement effective date")

# Route-level authorisation makes UI bypasses impossible.
loans_router = BACKEND / "routers/loans.py"
replace_once(loans_router, "from services.receipt_service import ensure_payment_receipt, generate_payment_receipt_pdf\n", "from services.receipt_service import ensure_payment_receipt, generate_payment_receipt_pdf\nfrom utils.payment_dates import assert_manual_backdate, resolve_effective_payment_date\n", "loans payment date import")
replace_once(loans_router, "    loan = loan_by_reference_or_404(db, payload.loan_reference)\n    assert_tenant_loan(context, loan)\n    payment, cash, preview = record_cash_repayment(\n", "    loan = loan_by_reference_or_404(db, payload.loan_reference)\n    assert_tenant_loan(context, loan)\n    effective_date = resolve_effective_payment_date(context.role, payload.payment_date)\n    assert_manual_backdate(payload.payment_method, effective_date)\n    payment, cash, preview = record_cash_repayment(\n", "cash route resolve date")
replace_once(loans_router, "        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n", "        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n        effective_date=effective_date,\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n", "cash route pass date")
replace_once(loans_router, "    payment = initiate_early_settlement_payment(\n        db,\n", "    effective_date = resolve_effective_payment_date(context.role, payload.payment_date)\n    assert_manual_backdate(payload.payment_method, effective_date)\n    payment = initiate_early_settlement_payment(\n        db,\n", "early route resolve date")
replace_once(loans_router, "        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n    )\n    db.refresh(quote)\n", "        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n        effective_date=effective_date,\n    )\n    db.refresh(quote)\n", "early route pass date")
replace_once(loans_router, "    loan = _tenant_loan_or_404(db, context, loan_id)\n    payment, cash, preview = record_installment_repayment(\n", "    loan = _tenant_loan_or_404(db, context, loan_id)\n    effective_date = resolve_effective_payment_date(context.role, payload.payment_date)\n    assert_manual_backdate(payload.payment_method, effective_date)\n    payment, cash, preview = record_installment_repayment(\n", "installment route resolve date")
# Use last installment call occurrence before receipt.
needle = "        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n"
text = loans_router.read_text()
if text.count(needle) != 1:
    raise SystemExit(f"installment route pass date: expected one remaining match, got {text.count(needle)}")
loans_router.write_text(text.replace(needle, "        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n        effective_date=effective_date,\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n", 1))

clients_router = BACKEND / "routers/company_clients.py"
replace_once(clients_router, "from services.receipt_service import ensure_payment_receipt\n", "from services.receipt_service import ensure_payment_receipt\nfrom utils.payment_dates import assert_manual_backdate, resolve_effective_payment_date\n", "client payment date import")
replace_once(clients_router, "    account = company_client_or_404(db, account_id=account_id, company_id=context.company_id)\n    assert_branch_scope(context, account.branch_id)\n    debt = _external_debt_or_404(db, account=account, debt_id=debt_id)\n", "    account = company_client_or_404(db, account_id=account_id, company_id=context.company_id)\n    assert_branch_scope(context, account.branch_id)\n    effective_date = resolve_effective_payment_date(context.role, payload.paid_on)\n    debt = _external_debt_or_404(db, account=account, debt_id=debt_id)\n", "external debt date policy")
replace_once(clients_router, "    event_at = datetime.combine(payload.paid_on, datetime.min.time(), tzinfo=timezone.utc)\n", "    event_at = datetime.combine(effective_date, datetime.min.time(), tzinfo=timezone.utc)\n", "external debt event date")
replace_once(clients_router, "    assert_branch_scope(context, account.branch_id)\n\n    amount = Decimal(account.opening_fee_amount or 0)\n", "    assert_branch_scope(context, account.branch_id)\n    effective_date = resolve_effective_payment_date(context.role, payload.payment_date)\n    assert_manual_backdate(payload.payment_method, effective_date)\n\n    amount = Decimal(account.opening_fee_amount or 0)\n", "opening fee date policy")
replace_once(clients_router, "        proof_notes=payload.proof_notes or payload.notes,\n    )\n", "        proof_notes=payload.proof_notes or payload.notes,\n        effective_date=effective_date,\n    )\n", "opening fee pass effective date")

# Pure policy tests.
test = BACKEND / "tests/test_payment_date_policy.py"
test.write_text('''from datetime import date

import pytest
from fastapi import HTTPException

from database.models.enums import UserRole
from utils.payment_dates import resolve_effective_payment_date

TODAY = date(2026, 9, 8)


def test_company_owner_can_backdate_payment():
    assert resolve_effective_payment_date(UserRole.COMPANY_OWNER, date(2024, 1, 15), today=TODAY) == date(2024, 1, 15)


def test_non_owner_cannot_backdate_payment():
    with pytest.raises(HTTPException) as exc:
        resolve_effective_payment_date(UserRole.COMPANY_ADMIN, date(2024, 1, 15), today=TODAY)
    assert exc.value.status_code == 403


def test_future_payment_date_is_blocked_even_for_owner():
    with pytest.raises(HTTPException) as exc:
        resolve_effective_payment_date(UserRole.COMPANY_OWNER, date(2026, 9, 9), today=TODAY)
    assert exc.value.status_code == 422


def test_missing_payment_date_defaults_to_business_today():
    assert resolve_effective_payment_date(UserRole.FINANCE_OFFICER, None, today=TODAY) == TODAY
''')

# Generate an Alembic migration against the actual current head.
versions = BACKEND / "alembic/versions"
revision = "b7c2e91fa604"
migration = versions / f"{revision}_add_payment_effective_date.py"
if not migration.exists():
    revisions: dict[str, str | tuple[str, ...] | None] = {}
    referenced: set[str] = set()
    for item in versions.glob("*.py"):
        source = item.read_text()
        rev_match = re.search(r'^revision\s*(?::[^=]+)?=\s*[\"\']([^\"\']+)[\"\']', source, re.MULTILINE)
        down_match = re.search(r'^down_revision\s*(?::[^=]+)?=\s*(.+)$', source, re.MULTILINE)
        if not rev_match:
            continue
        rev = rev_match.group(1)
        revisions[rev] = None
        if down_match:
            raw = down_match.group(1).strip()
            for parent in re.findall(r'[\"\']([^\"\']+)[\"\']', raw):
                referenced.add(parent)
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise SystemExit(f"Expected one Alembic head before payment-date migration, found {heads}")
    down_revision = heads[0]
    migration.write_text(f'''\"\"\"add effective payment date\n\nRevision ID: {revision}\nRevises: {down_revision}\n\"\"\"\nfrom alembic import op\nimport sqlalchemy as sa\n\nrevision = \"{revision}\"\ndown_revision = \"{down_revision}\"\nbranch_labels = None\ndepends_on = None\n\n\ndef upgrade():\n    op.add_column(\"payment_transactions\", sa.Column(\"effective_date\", sa.Date(), server_default=sa.text(\"CURRENT_DATE\"), nullable=True))\n    op.execute(\"UPDATE payment_transactions SET effective_date = COALESCE(DATE(completed_at), DATE(created_at), CURRENT_DATE) WHERE effective_date IS NULL\")\n    op.alter_column(\"payment_transactions\", \"effective_date\", nullable=False)\n    op.create_index(\"ix_payment_transactions_effective_date\", \"payment_transactions\", [\"effective_date\"], unique=False)\n\n\ndef downgrade():\n    op.drop_index(\"ix_payment_transactions_effective_date\", table_name=\"payment_transactions\")\n    op.drop_column(\"payment_transactions\", \"effective_date\")\n''')

# Frontend API contracts.
loans_api = FRONTEND / "api/loans.ts"
replace_once(loans_api, "  payment_method: PaymentMethod;\n  gateway_provider?: string | null;\n", "  payment_method: PaymentMethod;\n  payment_date?: string | null;\n  gateway_provider?: string | null;\n", "collect repayment api date")
# Installment payload has the same opening; replace second occurrence by targeted class text.
replace_once(loans_api, "export type InstallmentPaymentPayload = {\n  amount_tendered: number;\n  payment_method: PaymentMethod;\n", "export type InstallmentPaymentPayload = {\n  amount_tendered: number;\n  payment_method: PaymentMethod;\n  payment_date?: string | null;\n", "installment api date")
replace_once(loans_api, "    payment_method: PaymentMethod;\n    gateway_provider?: string | null;\n", "    payment_method: PaymentMethod;\n    payment_date?: string | null;\n    gateway_provider?: string | null;\n", "early settlement api date")

clients_api = FRONTEND / "api/companyClients.ts"
replace_once(clients_api, "    payment_method: PaymentMethod;\n    proof_reference?: string | null;\n", "    payment_method: PaymentMethod;\n    payment_date?: string | null;\n    proof_reference?: string | null;\n", "opening fee api date")

# Cashier: owner-only date selection; all users post today's date by default.
cashier = FRONTEND / "app/(dashboard)/company/cashier/page.tsx"
replace_once(cashier, "function dayAfterIsoDate(value: string): string {\n", "function todayIso(): string {\n  return new Date().toISOString().slice(0, 10);\n}\n\nfunction dayAfterIsoDate(value: string): string {\n", "cashier today helper")
replace_once(cashier, "  const canAdjustDueDates = hasRole(activeRole, LENDING_ROLES);\n  const canSettleEarly = hasRole(activeRole, FINANCE_ROLES);\n", "  const canAdjustDueDates = hasRole(activeRole, LENDING_ROLES);\n  const canSettleEarly = hasRole(activeRole, FINANCE_ROLES);\n  const canBackdatePayments = activeRole === \"company_owner\";\n", "cashier owner permission")
replace_once(cashier, "  const [action, setAction] = useState<OverpaymentAction>(\"carry_forward\");\n", "  const [action, setAction] = useState<OverpaymentAction>(\"carry_forward\");\n  const [paymentDate, setPaymentDate] = useState(todayIso());\n", "cashier payment date state")
replace_once(cashier, "    setAction(\"carry_forward\");\n    setEvidence(EMPTY_PAYMENT_EVIDENCE);\n", "    setAction(\"carry_forward\");\n    setPaymentDate(todayIso());\n    setEvidence(EMPTY_PAYMENT_EVIDENCE);\n", "cashier reset payment date")
replace_once(cashier, "        payment_method: evidence.payment_method,\n        gateway_provider: evidence.gateway_provider || null,\n", "        payment_method: evidence.payment_method,\n        payment_date: paymentDate,\n        gateway_provider: evidence.gateway_provider || null,\n", "cashier submit payment date")
replace_once(cashier, "          <DialogFooter className=\"mx-0 mb-0 flex-wrap\">\n", "          <div className=\"rounded-2xl border bg-muted/30 p-4\">\n            <Label htmlFor=\"cashier-payment-date\">Payment date</Label>\n            <Input id=\"cashier-payment-date\" className=\"mt-2\" type=\"date\" value={paymentDate} min={canBackdatePayments && isCash ? undefined : todayIso()} max={todayIso()} disabled={!canBackdatePayments || !isCash} onChange={(event) => setPaymentDate(event.target.value)} />\n            <p className=\"mt-2 text-xs text-muted-foreground\">{canBackdatePayments && isCash ? \"Company Owner may select an earlier effective date for historical cash records. The audit timestamp still records when this entry was actually posted.\" : \"Only Company Owner can backdate manually recorded cash payments.\"}</p>\n          </div>\n          <DialogFooter className=\"mx-0 mb-0 flex-wrap\">\n", "cashier confirm date UI")

# External-debt tracker already has a date picker; lock historical dates for non-owners.
ext_tracker = FRONTEND / "components/clients/external-debt-tracker.tsx"
text = ext_tracker.read_text()
if 'from "@/provider/tenantProvider"' not in text:
    insert_after = 'import { toast } from "@/utils/toast";\n'
    if insert_after not in text:
        raise SystemExit("external tracker tenant import anchor missing")
    text = text.replace(insert_after, insert_after + 'import { useTenant } from "@/provider/tenantProvider";\n', 1)
# add permission just inside component using first known state anchor
component_match = re.search(r'(export function ExternalDebtTracker\([^\)]*\) \{\n)', text)
if not component_match:
    raise SystemExit("external tracker component anchor missing")
pos = component_match.end()
text = text[:pos] + '  const { activeRole } = useTenant();\n  const canBackdatePayments = activeRole === "company_owner";\n' + text[pos:]
old_date = '<Field label="Payment date"><Input type="date" max={todayIso()} value={payment.paid_on} onChange={(event) => setPayment((current) => ({ ...current, paid_on: event.target.value }))} /></Field>'
new_date = '<Field label="Payment date"><Input type="date" min={canBackdatePayments ? undefined : todayIso()} max={todayIso()} value={payment.paid_on} onChange={(event) => setPayment((current) => ({ ...current, paid_on: event.target.value }))} /><p className="mt-1 text-xs text-muted-foreground">{canBackdatePayments ? "Company Owner may record the historical payment date." : "Backdating is restricted to Company Owner."}</p></Field>'
if old_date not in text:
    raise SystemExit("external tracker date input anchor missing")
text = text.replace(old_date, new_date, 1)
ext_tracker.write_text(text)

# Opening fee: owner can choose an earlier cash-payment date.
clients_page = FRONTEND / "app/(dashboard)/company/clients/page.tsx"
text = clients_page.read_text()
if 'from "@/provider/tenantProvider"' not in text:
    anchor = 'import { formatDate, formatMoney, titleCase } from "@/lib/format";\n'
    text = text.replace(anchor, anchor + 'import { useTenant } from "@/provider/tenantProvider";\n', 1)
text = text.replace('export default function CompanyClientsPage() {\n  const router = useRouter();\n', 'export default function CompanyClientsPage() {\n  const router = useRouter();\n  const { activeRole } = useTenant();\n  const canBackdatePayments = activeRole === "company_owner";\n', 1)
text = text.replace('  const [feeEvidence, setFeeEvidence] = useState<PaymentEvidence>(EMPTY_PAYMENT_EVIDENCE);\n', '  const [feeEvidence, setFeeEvidence] = useState<PaymentEvidence>(EMPTY_PAYMENT_EVIDENCE);\n  const [feePaymentDate, setFeePaymentDate] = useState(() => new Date().toISOString().slice(0, 10));\n', 1)
text = text.replace('    setFeeEvidence(EMPTY_PAYMENT_EVIDENCE);\n    setFeeDialog(true);\n', '    setFeeEvidence(EMPTY_PAYMENT_EVIDENCE);\n    setFeePaymentDate(new Date().toISOString().slice(0, 10));\n    setFeeDialog(true);\n', 1)
text = text.replace('        payment_method: feeEvidence.payment_method,\n        proof_reference:', '        payment_method: feeEvidence.payment_method,\n        payment_date: feePaymentDate,\n        proof_reference:', 1)
fee_anchor = '          <PaymentMethodFields methods={paymentMethods} value={feeEvidence} onChange={setFeeEvidence} />\n'
if fee_anchor not in text:
    raise SystemExit("opening fee UI anchor missing")
fee_ui = fee_anchor + '          <Field label="Payment date" description={canBackdatePayments && feeEvidence.payment_method === "cash" ? "Company Owner may select an earlier date for a historical cash payment; the actual entry timestamp remains in the audit trail." : "Only Company Owner can backdate manually recorded cash payments."}><Input type="date" value={feePaymentDate} min={canBackdatePayments && feeEvidence.payment_method === "cash" ? undefined : new Date().toISOString().slice(0, 10)} max={new Date().toISOString().slice(0, 10)} disabled={!canBackdatePayments || feeEvidence.payment_method !== "cash"} onChange={(event) => setFeePaymentDate(event.target.value)} /></Field>\n'
text = text.replace(fee_anchor, fee_ui, 1)
clients_page.write_text(text)

# Frontend PaymentTransaction type can surface the business date to registers/reports.
payment_type = FRONTEND / "types/payment.ts"
text = payment_type.read_text()
if "effective_date" not in text:
    text = text.replace("  amount: number;\n", "  amount: number;\n  effective_date: string;\n", 1)
payment_type.write_text(text)

print("Owner-only payment backdating policy applied across manual LoanHub payment paths.")
