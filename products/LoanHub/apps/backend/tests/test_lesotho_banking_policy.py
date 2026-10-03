import pytest
from pydantic import ValidationError

from database.schemas.company_clients import CompanyClientBankAccountUpdate
from database.schemas.employee import EmployeeProfileUpdate
from database.schemas.origination import BankAccountInput
from utils.banking import (
    DEFAULT_BANK_BRANCH,
    bank_account_digits_for,
    bank_code_for,
    validate_account_number_for_bank,
)


@pytest.mark.parametrize(
    ("bank_name", "code", "expected_digits", "account_number"),
    [
        ("FNB", "280061", 11, "61234567890"),
        ("PB", "500100", 13, "1012345678901"),
        ("STD", "060667", 13, "9012345678901"),
        ("NB", "390161", 11, "11123456789"),
        ("NB", "390161", 11, "12123456789"),
    ],
)
def test_supported_banks_have_fixed_codes_prefixes_and_digit_counts(
    bank_name,
    code,
    expected_digits,
    account_number,
):
    assert bank_code_for(bank_name) == code
    assert bank_account_digits_for(bank_name) == expected_digits
    assert validate_account_number_for_bank(bank_name, account_number) == account_number


@pytest.mark.parametrize(
    ("bank_name", "account_number", "expected_digits"),
    [
        ("FNB", "6123456789", 11),
        ("FNB", "612345678901", 11),
        ("PB", "101234567890", 13),
        ("PB", "10123456789012", 13),
        ("STD", "901234567890", 13),
        ("STD", "90123456789012", 13),
        ("NB", "1112345678", 11),
        ("NB", "111234567890", 11),
    ],
)
def test_account_number_must_match_bank_fixed_digit_count(
    bank_name,
    account_number,
    expected_digits,
):
    with pytest.raises(ValueError, match=rf"{bank_name} account number must contain exactly {expected_digits} digits"):
        validate_account_number_for_bank(bank_name, account_number)


def test_account_number_must_match_selected_bank():
    with pytest.raises(ValueError, match="FNB account number must start with 6"):
        validate_account_number_for_bank("FNB", "90123456789")

    with pytest.raises(ValueError, match="digits only"):
        validate_account_number_for_bank("PB", "10ABC12345678")


def test_origination_bank_account_is_normalized_to_fixed_branch_code_and_length():
    account = BankAccountInput(
        account_holder="Test Borrower",
        bank_name="fnb",
        branch_name="User supplied branch",
        branch_code="999999",
        account_number="6 1234 567890",
    )

    assert account.bank_name == "FNB"
    assert account.branch_name == DEFAULT_BANK_BRANCH
    assert account.branch_code == "280061"
    assert account.account_number == "61234567890"


def test_origination_rejects_unsupported_bank():
    with pytest.raises(ValidationError, match="Bank must be one of FNB, PB, STD or NB"):
        BankAccountInput(
            account_holder="Test Borrower",
            bank_name="Example Bank",
            account_number="61234567890",
        )


def test_client_profile_bank_change_requires_matching_new_account_number():
    with pytest.raises(ValidationError, match="Changing the bank requires"):
        CompanyClientBankAccountUpdate(bank_name="STD")

    update = CompanyClientBankAccountUpdate(
        bank_name="STD",
        account_number="9012345678901",
        branch_name="Wrong branch",
        branch_code="999999",
    )
    assert update.bank_name == "STD"
    assert update.branch_name == DEFAULT_BANK_BRANCH
    assert update.branch_code == "060667"


def test_client_profile_non_bank_partial_edit_remains_supported():
    update = CompanyClientBankAccountUpdate(account_holder="Updated Holder")
    assert update.account_holder == "Updated Holder"
    assert update.bank_name is None
    assert update.account_number is None


def test_employee_payroll_bank_account_uses_same_policy():
    profile = EmployeeProfileUpdate(
        employee_number="EMP-001",
        bank_name="nb",
        bank_account_name="Payroll Employee",
        bank_account_number="12 1234 56789",
    )
    assert profile.bank_name == "NB"
    assert profile.bank_account_number == "12123456789"


def test_employee_bank_account_requires_supported_bank_and_matching_prefix():
    with pytest.raises(ValidationError, match="Select FNB, PB, STD or NB"):
        EmployeeProfileUpdate(
            employee_number="EMP-002",
            bank_account_number="61234567890",
        )

    with pytest.raises(ValidationError, match="PB account number must start with 10"):
        EmployeeProfileUpdate(
            employee_number="EMP-003",
            bank_name="PB",
            bank_account_number="6012345678901",
        )


def test_employee_partial_update_keeps_omitted_banking_fields_unset():
    profile = EmployeeProfileUpdate(
        employee_number="EMP-004",
        job_title="Credit Analyst",
    )

    update = profile.model_dump(exclude_unset=True)
    assert update["employee_number"] == "EMP-004"
    assert update["job_title"] == "Credit Analyst"
    assert "bank_name" not in update
    assert "bank_account_number" not in update


def test_employee_can_explicitly_clear_bank_pair_without_partial_inconsistency():
    profile = EmployeeProfileUpdate(
        employee_number="EMP-005",
        bank_name=None,
        bank_account_number=None,
    )

    update = profile.model_dump(exclude_unset=True)
    assert update["bank_name"] is None
    assert update["bank_account_number"] is None
