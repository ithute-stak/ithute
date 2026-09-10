import pytest
from fastapi import HTTPException

from services.employer_group_service import normalize_employer_group_code
from utils.work_group_policy import (
    WORK_GROUP_CODES,
    is_supported_work_group,
    work_group_policy_for,
)


EXPECTED_WORK_GROUPS = (
    "L/GOV",
    "LMPS",
    "LCS",
    "LDF",
    "NSS",
    "NDSO",
    "PENSIONS",
    "NGO",
    "LEMS",
    "LE HAE",
)


def test_central_work_group_policy_contains_exact_supported_catalogue():
    assert WORK_GROUP_CODES == EXPECTED_WORK_GROUPS


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("L/Gov", "L/GOV"),
        (" l/gov ", "L/GOV"),
        ("LMPs", "LMPS"),
        ("NSs", "NSS"),
        ("le   hae", "LE HAE"),
        ("Lesotho Government", "L/GOV"),
        ("Lesotho Mounted Police Service", "LMPS"),
    ],
)
def test_work_group_aliases_are_canonicalized(raw: str, expected: str):
    policy = work_group_policy_for(raw)
    assert policy is not None
    assert policy.code == expected
    assert is_supported_work_group(raw)


@pytest.mark.parametrize("code", EXPECTED_WORK_GROUPS)
def test_employer_group_code_normalizer_accepts_only_central_codes(code: str):
    assert normalize_employer_group_code(code) == code


def test_arbitrary_employer_group_code_is_rejected():
    with pytest.raises(HTTPException) as exc:
        normalize_employer_group_code("ACME LTD")

    assert exc.value.status_code == 422
    assert "central work groups" in str(exc.value.detail)
