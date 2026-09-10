from __future__ import annotations

import re
from types import MappingProxyType

from fastapi import HTTPException, status


# LoanHub central Work Group policy. These are the only work groups that may be
# selected for employment classification. Keep codes stable because downstream
# collection grouping combines the work-group code with the bank code.
WORK_GROUP_POLICY = MappingProxyType(
    {
        "L/GOV": "Lesotho Government",
        "LMPS": "Lesotho Mounted Police Service",
        "LCS": "Lesotho Correctional Service",
        "LDF": "Lesotho Defence Force",
        "NSS": "National Security Service",
        "NDSO": "NDSO",
        "PENSIONS": "Pensions",
        "NGO": "NGO",
        "LEMS": "LEMS",
        "LE HAE": "LE HAE",
    }
)

# Common historical/input variants. Case-only variants such as LMPs, NSs and
# L/Gov are also handled by upper-casing before this alias lookup.
WORK_GROUP_ALIASES = MappingProxyType(
    {
        "LGOV": "L/GOV",
        "L GOV": "L/GOV",
        "L-GOV": "L/GOV",
        "LESOTHO GOVERNMENT": "L/GOV",
        "LESOTHO MOUNTED POLICE SERVICE": "LMPS",
        "LESOTHO CORRECTIONAL SERVICE": "LCS",
        "LESOTHO DEFENCE FORCE": "LDF",
        "NATIONAL SECURITY SERVICE": "NSS",
        "PENSION": "PENSIONS",
        "PENSIONER": "PENSIONS",
        "PENSIONERS": "PENSIONS",
    }
)

CANONICAL_WORK_GROUP_CODES = tuple(WORK_GROUP_POLICY.keys())


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).upper()


def normalize_work_group_code(value: str) -> str:
    """Return a canonical LoanHub work-group code or reject an unknown value."""
    code = _clean(value)
    code = WORK_GROUP_ALIASES.get(code, code)
    if code not in WORK_GROUP_POLICY:
        allowed = ", ".join(CANONICAL_WORK_GROUP_CODES)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Select a valid LoanHub work group. Allowed groups: {allowed}.",
        )
    return code


def canonical_work_group_name(code: str) -> str:
    return WORK_GROUP_POLICY[normalize_work_group_code(code)]
