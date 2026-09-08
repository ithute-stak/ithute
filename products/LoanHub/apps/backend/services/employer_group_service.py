from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models.employer_group import EmployerGroup
from database.schemas.employer_group import EmployerGroupCreate


_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9 /._&-]{0,39}$")


def normalize_employer_group_code(value: str) -> str:
    code = re.sub(r"\s+", " ", str(value or "").strip()).upper()
    if not code or not _CODE_PATTERN.fullmatch(code):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Employer/group code must contain letters, numbers or the supported "
                "separators / . _ & - and be at most 40 characters."
            ),
        )
    return code


def normalize_employer_group_name(value: str) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    if len(name) < 2 or len(name) > 200:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Employer/group name must be between 2 and 200 characters.",
        )
    return name


def resolve_employer_group(
    db: Session,
    *,
    employer_group_id: UUID | None = None,
    new_employer_group: EmployerGroupCreate | None = None,
) -> EmployerGroup | None:
    if employer_group_id and new_employer_group is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select an existing employer group or add a new one, not both.",
        )

    if employer_group_id:
        group = (
            db.query(EmployerGroup)
            .filter(
                EmployerGroup.id == employer_group_id,
                EmployerGroup.is_active.is_(True),
            )
            .first()
        )
        if group is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="The selected employer/group is not available.",
            )
        return group

    if new_employer_group is None:
        return None

    code = normalize_employer_group_code(new_employer_group.code)
    name = normalize_employer_group_name(new_employer_group.name)
    existing = db.query(EmployerGroup).filter(EmployerGroup.code == code).first()
    if existing is not None:
        if not existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="That employer/group code exists but is inactive.",
            )
        return existing

    group = EmployerGroup(code=code, name=name, is_active=True)
    db.add(group)
    db.flush()
    return group
