from pathlib import Path

ROOT = Path('products/LoanHub')


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 match, found {count}')
    path.write_text(text.replace(old, new, 1))


# 1. Central backend policy: only company_owner may choose an earlier payment date.
policy = ROOT / 'apps/backend/utils/payment_dates.py'
policy.write_text('''from datetime import date, datetime, time, timezone\nfrom zoneinfo import ZoneInfo\n\nfrom fastapi import HTTPException\n\nfrom database.config.config import settings\nfrom database.models.enums import UserRole\n\n\ndef current_payment_date() -> date:\n    return datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()\n\n\ndef resolve_payment_date(role: UserRole, requested: date | None, *, today: date | None = None) -> date:\n    current = today or current_payment_date()\n    effective = requested or current\n    if effective > current:\n        raise HTTPException(status_code=422, detail="Payment date cannot be in the future")\n    if effective < current and role != UserRole.COMPANY_OWNER:\n        raise HTTPException(status_code=403, detail="Only the Company Owner can backdate payments")\n    return effective\n\n\ndef payment_date_to_utc(value: date) -> datetime:\n    local_midnight = datetime.combine(value, time.min, tzinfo=ZoneInfo(settings.APP_TIMEZONE))\n    return local_midnight.astimezone(timezone.utc)\n''')

# 2. API schemas accept a date, but authorization remains server-side.
cash_schema = ROOT / 'apps/backend/database/schemas/cash.py'
replace_once(
    cash_schema,
    'class CashRepaymentPreviewCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n',
    'class CashRepaymentPreviewCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n    payment_date: date | None = None\n',
    'cash repayment payment_date',
)
replace_once(
    cash_schema,
    'class InstallmentPaymentCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n',
    'class InstallmentPaymentCreate(BaseModel):\n    payment_method: PaymentMethod = PaymentMethod.CASH\n    payment_date: date | None = None\n',
    'installment payment_date',
)

# 3. Router enforces Company Owner-only backdating on every ordinary repayment write path.
loans_router = ROOT / 'apps/backend/routers/loans.py'
replace_once(
    loans_router,
    'from services.receipt_service import ensure_payment_receipt, generate_payment_receipt_pdf\n',
    'from services.receipt_service import ensure_payment_receipt, generate_payment_receipt_pdf\nfrom utils.payment_dates import current_payment_date, resolve_payment_date\n',
    'loans router payment date import',
)
replace_once(
    loans_router,
    '''    loan = loan_by_reference_or_404(db, payload.loan_reference)\n    assert_tenant_loan(context, loan)\n    return preview_cash_repayment(\n        loan,\n        amount_tendered=payload.amount_tendered,\n        overpayment_action=payload.overpayment_action,\n        installment_number=payload.installment_number,\n    )\n''',
    '''    loan = loan_by_reference_or_404(db, payload.loan_reference)\n    assert_tenant_loan(context, loan)\n    effective_payment_date = resolve_payment_date(context.role, payload.payment_date)\n    return preview_cash_repayment(\n        loan,\n        amount_tendered=payload.amount_tendered,\n        overpayment_action=payload.overpayment_action,\n        installment_number=payload.installment_number,\n        payment_date=effective_payment_date,\n    )\n''',
    'repayment preview policy',
)
replace_once(
    loans_router,
    '''    loan = loan_by_reference_or_404(db, payload.loan_reference)\n    assert_tenant_loan(context, loan)\n    payment, cash, preview = record_cash_repayment(\n''',
    '''    loan = loan_by_reference_or_404(db, payload.loan_reference)\n    assert_tenant_loan(context, loan)\n    effective_payment_date = resolve_payment_date(context.role, payload.payment_date)\n    payment, cash, preview = record_cash_repayment(\n''',
    'cash repayment effective date',
)
replace_once(
    loans_router,
    '''        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n''',
    '''        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n        payment_date=effective_payment_date,\n        backdated_by_company_owner=(\n            context.role == UserRole.COMPANY_OWNER\n            and effective_payment_date < current_payment_date()\n        ),\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n''',
    'cash repayment service date',
)
replace_once(
    loans_router,
    '''    require_tenant_roles(context, INSTALLMENT_PAYMENT_ROLES)\n    loan = _tenant_loan_or_404(db, context, loan_id)\n    payment, cash, preview = record_installment_repayment(\n''',
    '''    require_tenant_roles(context, INSTALLMENT_PAYMENT_ROLES)\n    loan = _tenant_loan_or_404(db, context, loan_id)\n    effective_payment_date = resolve_payment_date(context.role, payload.payment_date)\n    payment, cash, preview = record_installment_repayment(\n''',
    'installment repayment effective date',
)
replace_once(
    loans_router,
    '''        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n    return {\n        "payment_id": payment.id,\n''',
    '''        notes=payload.notes,\n        idempotency_key=payload.idempotency_key,\n        payment_date=effective_payment_date,\n        backdated_by_company_owner=(\n            context.role == UserRole.COMPANY_OWNER\n            and effective_payment_date < current_payment_date()\n        ),\n    )\n    receipt_number, receipt_file = payment_receipt_payload(db, payment.id)\n    return {\n        "payment_id": payment.id,\n''',
    'installment service date',
)

# 4. Repayment engine uses the effective date for payoff logic, payment completion, and installment paid_at.
service = ROOT / 'apps/backend/services/loan_service.py'
replace_once(
    service,
    'from services.interest_calculation_service import calculate_loan_terms\n',
    'from services.interest_calculation_service import calculate_loan_terms\nfrom utils.payment_dates import payment_date_to_utc\n',
    'loan service payment date import',
)
replace_once(
    service,
    '''    amount_tendered: Decimal,\n    overpayment_action: str,\n    installment_number: int | None = None,\n) -> dict[str, Any]:\n''',
    '''    amount_tendered: Decimal,\n    overpayment_action: str,\n    installment_number: int | None = None,\n    payment_date: date | None = None,\n) -> dict[str, Any]:\n''',
    'preview payment_date signature',
)
replace_once(
    service,
    '''    early_settlement_required, future_installments = early_settlement_required_for_payoff(\n        loan,\n        amount_applied=applied,\n    )\n''',
    '''    early_settlement_required, future_installments = early_settlement_required_for_payoff(\n        loan,\n        amount_applied=applied,\n        as_of_date=payment_date,\n    )\n''',
    'preview as-of payment date',
)
replace_once(
    service,
    '''    notes: str | None = None,\n    idempotency_key: str | None = None,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    """Post a loan repayment through cash or a manually verified channel."""\n''',
    '''    notes: str | None = None,\n    idempotency_key: str | None = None,\n    payment_date: date | None = None,\n    backdated_by_company_owner: bool = False,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    """Post a loan repayment through cash or a manually verified channel."""\n''',
    'record repayment signature',
)
replace_once(
    service,
    '''        overpayment_action=overpayment_action,\n        installment_number=installment_number,\n    )\n''',
    '''        overpayment_action=overpayment_action,\n        installment_number=installment_number,\n        payment_date=payment_date,\n    )\n''',
    'record repayment preview date',
)
replace_once(
    service,
    '''    now = datetime.now(timezone.utc)\n    reference = _recorded_payment_reference(payment_method, PaymentDirection.INBOUND, proof_reference)\n''',
    '''    now = datetime.now(timezone.utc)\n    effective_at = payment_date_to_utc(payment_date) if payment_date else now\n    reference = _recorded_payment_reference(payment_method, PaymentDirection.INBOUND, proof_reference)\n''',
    'repayment effective timestamp',
)
replace_once(
    service,
    '''            "forward_amount": str(preview["forward_amount"]),\n            "notes": notes,\n        },\n        completed_at=now,\n''',
    '''            "forward_amount": str(preview["forward_amount"]),\n            "notes": notes,\n            "effective_payment_date": payment_date.isoformat() if payment_date else None,\n            "backdated_by_company_owner": backdated_by_company_owner,\n        },\n        completed_at=effective_at,\n''',
    'repayment provider metadata',
)
replace_once(
    service,
    '''    notes: str | None = None,\n    idempotency_key: str | None = None,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    """Record a payment against the current installment only.\n''',
    '''    notes: str | None = None,\n    idempotency_key: str | None = None,\n    payment_date: date | None = None,\n    backdated_by_company_owner: bool = False,\n) -> tuple[PaymentTransaction, CashTransaction | None, dict[str, Any]]:\n    """Record a payment against the current installment only.\n''',
    'installment repayment signature',
)
replace_once(
    service,
    '''        notes=notes,\n        idempotency_key=idempotency_key,\n    )\n\n\ndef allocate_repayment''',
    '''        notes=notes,\n        idempotency_key=idempotency_key,\n        payment_date=payment_date,\n        backdated_by_company_owner=backdated_by_company_owner,\n    )\n\n\ndef allocate_repayment''',
    'installment pass payment date',
)
replace_once(
    service,
    '''def allocate_repayment(db: Session, payment: PaymentTransaction) -> None:\n    loan = payment.loan or db.get(ClientCompanyLoan, payment.loan_id)\n''',
    '''def allocate_repayment(db: Session, payment: PaymentTransaction) -> None:\n    loan = payment.loan or db.get(ClientCompanyLoan, payment.loan_id)\n''',
    'allocate anchor',
)
replace_once(
    service,
    '''        if Decimal(installment.paid_amount) >= Decimal(installment.total_due):\n            installment.status = InstallmentStatus.PAID\n            installment.paid_at = datetime.now(timezone.utc)\n''',
    '''        if Decimal(installment.paid_amount) >= Decimal(installment.total_due):\n            installment.status = InstallmentStatus.PAID\n            installment.paid_at = payment.completed_at or datetime.now(timezone.utc)\n''',
    'installment paid_at effective date',
)

# 5. Accounting follows effective payment date even for an owner-imported closed historical period.
accounting = ROOT / 'apps/backend/services/accounting_service.py'
replace_once(
    accounting,
    '''    status_value: str = "draft",\n) -> JournalEntry:\n    from services.governance_control_service import ensure_accounting_period_open\n\n    ensure_accounting_period_open(db, company_id=company_id, entry_date=entry_date)\n''',
    '''    status_value: str = "draft",\n    allow_closed_period: bool = False,\n) -> JournalEntry:\n    from services.governance_control_service import ensure_accounting_period_open\n\n    if not allow_closed_period:\n        ensure_accounting_period_open(db, company_id=company_id, entry_date=entry_date)\n''',
    'accounting owner historical override',
)
replace_once(
    accounting,
    '''        reference_id=str(source.id),\n        status_value="posted",\n''',
    '''        reference_id=str(source.id),\n        status_value="posted",\n        allow_closed_period=bool((source.provider_payload or {}).get("backdated_by_company_owner")),\n''',
    'payment accounting override flag',
)

# 6. Treasury follows effective date and explicitly reopens a submitted historical day for owner-imported payment.
treasury = ROOT / 'apps/backend/services/treasury_service.py'
replace_once(
    treasury,
    '''    ledger = ensure_current_payment_day_writable(\n        db,\n        ledger,\n        settings=settings,\n        occurred_at=occurred_at,\n    )\n    assert_ledger_writable(ledger)\n''',
    '''    owner_backdated = bool((payment.provider_payload or {}).get("backdated_by_company_owner"))\n    if owner_backdated and ledger.status not in {TreasuryDayStatus.OPEN, TreasuryDayStatus.REOPENED}:\n        ledger = reopen_daily_ledger(\n            db,\n            ledger,\n            reason=(\n                "Company Owner posted a verified backdated payment. "\n                f"Payment {payment.provider_reference or payment.id} was applied to this historical business date."\n            ),\n        )\n    else:\n        ledger = ensure_current_payment_day_writable(\n            db,\n            ledger,\n            settings=settings,\n            occurred_at=occurred_at,\n        )\n    assert_ledger_writable(ledger)\n''',
    'treasury backdated owner ledger reopen',
)

# 7. Frontend API carries optional payment_date through both payment routes.
api = ROOT / 'apps/frontend/api/loans.ts'
replace_once(
    api,
    '''  payment_method?: PaymentMethod;\n}): Promise<CashRepaymentPreview> {\n''',
    '''  payment_method?: PaymentMethod;\n  payment_date?: string | null;\n}): Promise<CashRepaymentPreview> {\n''',
    'preview API payment date',
)
replace_once(
    api,
    '''  idempotency_key?: string;\n}): Promise<CashPaymentResult> {\n  return (await api.post<CashPaymentResult>("/loans/repayments", payload)).data;\n''',
    '''  idempotency_key?: string;\n  payment_date?: string | null;\n}): Promise<CashPaymentResult> {\n  return (await api.post<CashPaymentResult>("/loans/repayments", payload)).data;\n''',
    'collect API payment date',
)
replace_once(
    api,
    '''  idempotency_key?: string;\n};\n\nexport async function payLoanInstallment''',
    '''  idempotency_key?: string;\n  payment_date?: string | null;\n};\n\nexport async function payLoanInstallment''',
    'installment API payment date',
)

# 8. Payment desk exposes the date only to the active Company Owner role.
cashier = ROOT / 'apps/frontend/app/(dashboard)/company/cashier/page.tsx'
replace_once(
    cashier,
    '''function dayBeforeIsoDate(value: string): string {\n  const [year, month, day] = value.split("-").map(Number);\n  const previous = new Date(Date.UTC(year, month - 1, day - 1));\n  return previous.toISOString().slice(0, 10);\n}\n\nexport default function CompanyCashierPage() {\n''',
    '''function dayBeforeIsoDate(value: string): string {\n  const [year, month, day] = value.split("-").map(Number);\n  const previous = new Date(Date.UTC(year, month - 1, day - 1));\n  return previous.toISOString().slice(0, 10);\n}\n\nfunction localTodayIsoDate(): string {\n  const now = new Date();\n  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);\n  return local.toISOString().slice(0, 10);\n}\n\nexport default function CompanyCashierPage() {\n''',
    'cashier local today helper',
)
replace_once(
    cashier,
    '''  const canAdjustDueDates = hasRole(activeRole, LENDING_ROLES);\n  const canSettleEarly = hasRole(activeRole, FINANCE_ROLES);\n\n  const [loanReference''',
    '''  const canAdjustDueDates = hasRole(activeRole, LENDING_ROLES);\n  const canSettleEarly = hasRole(activeRole, FINANCE_ROLES);\n  const canBackdatePayments = activeRole === "company_owner";\n\n  const [loanReference''',
    'cashier owner backdate role',
)
replace_once(
    cashier,
    '''  const [amount, setAmount] = useState("");\n  const [action, setAction]''',
    '''  const [amount, setAmount] = useState("");\n  const [paymentDate, setPaymentDate] = useState(localTodayIsoDate);\n  const [action, setAction]''',
    'cashier payment date state',
)
replace_once(
    cashier,
    '''    setAmount("");\n    setPreview(null);\n    setAction("carry_forward");\n''',
    '''    setAmount("");\n    setPaymentDate(localTodayIsoDate());\n    setPreview(null);\n    setAction("carry_forward");\n''',
    'cashier reset payment date',
)
replace_once(
    cashier,
    '''        installment_number: selectedInstallment?.installment_number,\n        payment_method: evidence.payment_method,\n      });\n''',
    '''        installment_number: selectedInstallment?.installment_number,\n        payment_method: evidence.payment_method,\n        payment_date: canBackdatePayments ? paymentDate : null,\n      });\n''',
    'cashier preview payment date',
)
replace_once(
    cashier,
    '''        notes: evidence.proof_notes.trim() || undefined,\n        idempotency_key: createIdempotencyKey(`repayment-${evidence.payment_method}-${loan.id}`),\n      });\n''',
    '''        notes: evidence.proof_notes.trim() || undefined,\n        idempotency_key: createIdempotencyKey(`repayment-${evidence.payment_method}-${loan.id}`),\n        payment_date: canBackdatePayments ? paymentDate : null,\n      });\n''',
    'cashier collect payment date',
)
replace_once(
    cashier,
    '''              <PaymentMethodFields methods={methods} value={evidence} onChange={updateEvidence} />\n              <div className="space-y-2"><Label htmlFor="amount">Amount received</Label>''',
    '''              <PaymentMethodFields methods={methods} value={evidence} onChange={updateEvidence} />\n              {canBackdatePayments ? (\n                <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">\n                  <Label htmlFor="payment-date">Payment date</Label>\n                  <Input\n                    id="payment-date"\n                    type="date"\n                    max={localTodayIsoDate()}\n                    value={paymentDate}\n                    onChange={(event) => { setPaymentDate(event.target.value); setPreview(null); }}\n                  />\n                  <p className="text-xs text-muted-foreground">Company Owner control: choose the actual historical payment date for legacy records. Future dates are never allowed.</p>\n                </div>\n              ) : null}\n              <div className="space-y-2"><Label htmlFor="amount">Amount received</Label>''',
    'cashier payment date UI',
)

# 9. Focused policy tests.
test = ROOT / 'apps/backend/tests/test_payment_backdating_policy.py'
test.write_text('''from datetime import date\n\nimport pytest\nfrom fastapi import HTTPException\n\nfrom database.models.enums import UserRole\nfrom utils.payment_dates import resolve_payment_date\n\n\ndef test_company_owner_can_backdate_payment():\n    today = date(2026, 9, 8)\n    assert resolve_payment_date(UserRole.COMPANY_OWNER, date(2024, 1, 15), today=today) == date(2024, 1, 15)\n\n\ndef test_non_owner_cannot_backdate_payment():\n    with pytest.raises(HTTPException) as error:\n        resolve_payment_date(UserRole.COMPANY_ADMIN, date(2024, 1, 15), today=date(2026, 9, 8))\n    assert error.value.status_code == 403\n    assert "Only the Company Owner" in str(error.value.detail)\n\n\ndef test_all_payment_roles_can_use_today():\n    today = date(2026, 9, 8)\n    assert resolve_payment_date(UserRole.COMPANY_ADMIN, today, today=today) == today\n    assert resolve_payment_date(UserRole.FINANCE_OFFICER, None, today=today) == today\n\n\ndef test_future_payment_date_is_rejected_even_for_owner():\n    with pytest.raises(HTTPException) as error:\n        resolve_payment_date(UserRole.COMPANY_OWNER, date(2026, 9, 9), today=date(2026, 9, 8))\n    assert error.value.status_code == 422\n    assert "future" in str(error.value.detail).lower()\n''')

print('Owner-only LoanHub repayment backdating patch applied.')
