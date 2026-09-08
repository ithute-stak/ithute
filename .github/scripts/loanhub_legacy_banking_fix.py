from pathlib import Path

FRONTEND = Path("products/LoanHub/apps/frontend/app/(dashboard)/company/legacy-cashout-register/page.tsx")
SCHEMA = Path("products/LoanHub/apps/backend/database/schemas/legacy_cashout.py")
TESTS = Path("products/LoanHub/apps/backend/tests/test_legacy_cashout_schema.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def patch_backend() -> None:
    text = SCHEMA.read_text()
    text = replace_once(
        text,
        "from database.models.enums import RepaymentType\n",
        "from database.models.enums import RepaymentType\nfrom utils.banking import standard_bank_fields, validate_account_number_for_bank\n",
        "backend banking import",
    )
    text = replace_once(
        text,
        '''        account_number = "".join(character for character in self.bank_account_number if character.isalnum())
        if len(account_number) < 4:
            raise ValueError("A valid bank account number is required")
        self.bank_account_number = account_number
''',
        '''        try:
            bank_name, bank_branch_name, bank_branch_code = standard_bank_fields(self.bank_name)
            account_number = validate_account_number_for_bank(bank_name, self.bank_account_number)
        except ValueError as error:
            raise ValueError(str(error)) from error
        if account_number is None:
            raise ValueError("A valid bank account number is required")
        self.bank_name = bank_name
        self.bank_branch_name = bank_branch_name
        self.bank_branch_code = bank_branch_code
        self.bank_account_number = account_number
''',
        "backend account policy",
    )
    SCHEMA.write_text(text)


def patch_frontend() -> None:
    text = FRONTEND.read_text()
    text = replace_once(
        text,
        'import { Input } from "@/components/ui/input";\n',
        'import { Input } from "@/components/ui/input";\nimport { NativeSelect } from "@/components/ui/native-select";\n',
        "frontend select import",
    )
    text = replace_once(
        text,
        'import { INTEREST_METHOD_OPTIONS } from "@/lib/interest-methods";\n',
        '''import { INTEREST_METHOD_OPTIONS } from "@/lib/interest-methods";
import {
  BANK_NAMES,
  DEFAULT_BANK_BRANCH,
  bankAccountPrefixHint,
  bankAccountValidationMessage,
  bankDetails,
  isBankName,
  normalizeBankAccountNumber,
} from "@/lib/banking";
''',
        "frontend banking imports",
    )
    text = replace_once(
        text,
        '''  const isNationalId = useMemo(
    () => /^\\d+$/.test(form.identity_number.trim()),
    [form.identity_number],
  );
''',
        '''  const isNationalId = useMemo(
    () => /^\\d+$/.test(form.identity_number.trim()),
    [form.identity_number],
  );
  const selectedBankDetails = useMemo(() => bankDetails(form.bank_name), [form.bank_name]);
  const bankAccountError = useMemo(
    () => bankAccountValidationMessage(form.bank_name, form.bank_account_number),
    [form.bank_name, form.bank_account_number],
  );
  const legacyBank = form.bank_name && !isBankName(form.bank_name) ? form.bank_name : null;
''',
        "frontend banking state",
    )
    text = replace_once(
        text,
        '''      if (Object.keys(calculatorSnapshot).length === 0) {
        toast.error("Calculate the original loan with LoanHub before saving this entry.");
        return;
      }

      const payload: LegacyCashoutCaptureInput = {
''',
        '''      if (Object.keys(calculatorSnapshot).length === 0) {
        toast.error("Calculate the original loan with LoanHub before saving this entry.");
        return;
      }
      if (!isBankName(form.bank_name)) {
        toast.error("Select FNB, PB, STD or NB before saving this entry.");
        return;
      }
      if (bankAccountError) {
        toast.error(bankAccountError);
        return;
      }
      const banking = bankDetails(form.bank_name);
      if (!banking) {
        toast.error("Select a supported bank before saving this entry.");
        return;
      }

      const payload: LegacyCashoutCaptureInput = {
''',
        "frontend submit guard",
    )
    text = replace_once(
        text,
        '''        bank_name: form.bank_name,
        bank_account_holder: form.bank_account_holder,
        bank_account_number: form.bank_account_number,
        bank_branch_name: optional(form.bank_branch_name),
        bank_branch_code: optional(form.bank_branch_code),
''',
        '''        bank_name: banking.name,
        bank_account_holder: form.bank_account_holder,
        bank_account_number: normalizeBankAccountNumber(form.bank_account_number),
        bank_branch_name: banking.branch,
        bank_branch_code: banking.code,
''',
        "frontend canonical banking payload",
    )
    text = replace_once(
        text,
        '''            <Field label="Bank name" required><Input required value={form.bank_name} onChange={(event) => update("bank_name", event.target.value)} /></Field>
            <Field label="Account holder" required><Input required value={form.bank_account_holder} onChange={(event) => update("bank_account_holder", event.target.value)} /></Field>
            <Field label={editingId ? "Account number (re-enter to update)" : "Account number"} required><Input required type="password" autoComplete="off" placeholder={editingId ? "Enter the account number again" : undefined} value={form.bank_account_number} onChange={(event) => update("bank_account_number", event.target.value)} /></Field>
            <Field label="Branch name"><Input value={form.bank_branch_name} onChange={(event) => update("bank_branch_name", event.target.value)} /></Field>
            <Field label="Branch code"><Input value={form.bank_branch_code} onChange={(event) => update("bank_branch_code", event.target.value)} /></Field>
            <Field label="Account type"><Input value={form.bank_account_type} onChange={(event) => update("bank_account_type", event.target.value)} /></Field>
''',
        '''            <Field label="Bank name" required>
              <NativeSelect
                required
                value={form.bank_name}
                onChange={(event) => {
                  const bankName = event.target.value;
                  const details = bankDetails(bankName);
                  setForm((current) => ({
                    ...current,
                    bank_name: bankName,
                    bank_branch_name: details?.branch ?? current.bank_branch_name,
                    bank_branch_code: details?.code ?? current.bank_branch_code,
                  }));
                }}
              >
                <option value="">Select bank</option>
                {legacyBank ? <option value={legacyBank}>Legacy — {legacyBank} (select a supported bank to save)</option> : null}
                {BANK_NAMES.map((bankName) => <option key={bankName} value={bankName}>{bankName}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Account holder" required><Input required value={form.bank_account_holder} onChange={(event) => update("bank_account_holder", event.target.value)} /></Field>
            <Field label={editingId ? "Account number (re-enter to update)" : "Account number"} required>
              <div className="space-y-1">
                <Input
                  required
                  type="password"
                  inputMode="numeric"
                  autoComplete="off"
                  aria-invalid={Boolean(bankAccountError)}
                  placeholder={editingId ? "Enter the account number again" : undefined}
                  value={form.bank_account_number}
                  onChange={(event) => update("bank_account_number", event.target.value)}
                />
                <p className={`text-xs ${bankAccountError ? "text-destructive" : "text-muted-foreground"}`}>
                  {bankAccountError ?? bankAccountPrefixHint(form.bank_name)}
                </p>
              </div>
            </Field>
            <Field label="Branch name"><Input readOnly value={selectedBankDetails?.branch ?? (form.bank_branch_name || DEFAULT_BANK_BRANCH)} /></Field>
            <Field label="Branch code"><Input readOnly value={selectedBankDetails?.code ?? form.bank_branch_code} /></Field>
            <Field label="Account type"><Input value={form.bank_account_type} onChange={(event) => update("bank_account_type", event.target.value)} /></Field>
''',
        "frontend banking fields",
    )
    if 'Field label="Bank name" required><Input' in text:
        raise SystemExit("frontend: free-text bank input remains")
    if 'onChange={(event) => update("bank_branch_code"' in text:
        raise SystemExit("frontend: editable branch code remains")
    FRONTEND.write_text(text)


def patch_tests() -> None:
    text = TESTS.read_text()
    text = text.replace('"bank_name": "Example Bank",', '"bank_name": "FNB",')
    text = text.replace('"bank_account_number": "1234567890",', '"bank_account_number": "6123456789",')
    text = text.replace('bank_name="Example Bank",', 'bank_name="FNB",')
    text = text.replace('bank_account_number="0012345678",', 'bank_account_number="6012345678",')
    text = text.replace('assert capture.bank_account_number == "0012345678"', 'assert capture.bank_account_number == "6012345678"')
    text += '''


def test_legacy_capture_applies_standard_branch_and_code():
    capture = LegacyCashoutCaptureCreate(
        **_payload(
            bank_name="fnb",
            bank_account_number="6123-456-789",
            bank_branch_name="Historic branch",
            bank_branch_code="999999",
        )
    )
    assert capture.bank_name == "FNB"
    assert capture.bank_account_number == "6123456789"
    assert capture.bank_branch_name == "Maseru Central"
    assert capture.bank_branch_code == "280061"


def test_legacy_capture_rejects_unsupported_bank():
    with pytest.raises(ValidationError, match="Bank must be one of FNB, PB, STD or NB"):
        LegacyCashoutCaptureCreate(**_payload(bank_name="Example Bank"))


def test_legacy_capture_rejects_wrong_account_prefix():
    with pytest.raises(ValidationError, match="FNB account number must start with 6"):
        LegacyCashoutCaptureCreate(**_payload(bank_name="FNB", bank_account_number="9012345678"))
'''
    TESTS.write_text(text)


patch_backend()
patch_frontend()
patch_tests()
print("Legacy Cash-out Register banking policy patch applied.")
