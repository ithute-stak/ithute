from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()


def path(relative: str) -> Path:
    return ROOT / relative


def read(relative: str) -> str:
    return path(relative).read_text(encoding="utf-8")


def write(relative: str, content: str) -> None:
    target = path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(relative: str, old: str, new: str) -> None:
    content = read(relative)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {relative}, found {count}: {old[:120]!r}")
    write(relative, content.replace(old, new, 1))


# ---------------------------------------------------------------------------
# New backend catalog model/schema/service/router.
# ---------------------------------------------------------------------------
write(
    "products/LoanHub/apps/backend/database/models/employer_group.py",
    '''from sqlalchemy import Boolean, Column, String\nfrom sqlalchemy.orm import relationship\n\nfrom database.base import Base\n\n\nclass EmployerGroup(Base):\n    __tablename__ = "employer_groups"\n\n    code = Column(String(40), unique=True, nullable=False, index=True)\n    name = Column(String(200), nullable=False, index=True)\n    is_active = Column(Boolean, default=True, nullable=False, index=True)\n\n    borrowers = relationship(\n        "Borrower",\n        back_populates="employer_group",\n    )\n''',
)

write(
    "products/LoanHub/apps/backend/database/schemas/employer_group.py",
    '''from datetime import datetime\nfrom uuid import UUID\n\nfrom pydantic import BaseModel, ConfigDict, Field\n\n\nclass EmployerGroupCreate(BaseModel):\n    model_config = ConfigDict(extra="forbid")\n\n    code: str = Field(min_length=1, max_length=40)\n    name: str = Field(min_length=2, max_length=200)\n\n\nclass EmployerGroupRead(BaseModel):\n    id: UUID\n    code: str\n    name: str\n    is_active: bool\n    created_at: datetime\n    updated_at: datetime\n\n    model_config = ConfigDict(from_attributes=True)\n''',
)

write(
    "products/LoanHub/apps/backend/services/employer_group_service.py",
    '''from __future__ import annotations\n\nimport re\nfrom uuid import UUID\n\nfrom fastapi import HTTPException, status\nfrom sqlalchemy.orm import Session\n\nfrom database.models.employer_group import EmployerGroup\nfrom database.schemas.employer_group import EmployerGroupCreate\n\n\n_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9 /._&-]{0,39}$")\n\n\ndef normalize_employer_group_code(value: str) -> str:\n    code = re.sub(r"\\s+", " ", str(value or "").strip()).upper()\n    if not code or not _CODE_PATTERN.fullmatch(code):\n        raise HTTPException(\n            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,\n            detail=(\n                "Employer/group code must contain letters, numbers or the supported "\n                "separators / . _ & - and be at most 40 characters."\n            ),\n        )\n    return code\n\n\ndef normalize_employer_group_name(value: str) -> str:\n    name = re.sub(r"\\s+", " ", str(value or "").strip())\n    if len(name) < 2 or len(name) > 200:\n        raise HTTPException(\n            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,\n            detail="Employer/group name must be between 2 and 200 characters.",\n        )\n    return name\n\n\ndef resolve_employer_group(\n    db: Session,\n    *,\n    employer_group_id: UUID | None = None,\n    new_employer_group: EmployerGroupCreate | None = None,\n) -> EmployerGroup | None:\n    if employer_group_id and new_employer_group is not None:\n        raise HTTPException(\n            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,\n            detail="Select an existing employer group or add a new one, not both.",\n        )\n\n    if employer_group_id:\n        group = (\n            db.query(EmployerGroup)\n            .filter(\n                EmployerGroup.id == employer_group_id,\n                EmployerGroup.is_active.is_(True),\n            )\n            .first()\n        )\n        if group is None:\n            raise HTTPException(\n                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,\n                detail="The selected employer/group is not available.",\n            )\n        return group\n\n    if new_employer_group is None:\n        return None\n\n    code = normalize_employer_group_code(new_employer_group.code)\n    name = normalize_employer_group_name(new_employer_group.name)\n    existing = db.query(EmployerGroup).filter(EmployerGroup.code == code).first()\n    if existing is not None:\n        if not existing.is_active:\n            raise HTTPException(\n                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,\n                detail="That employer/group code exists but is inactive.",\n            )\n        return existing\n\n    group = EmployerGroup(code=code, name=name, is_active=True)\n    db.add(group)\n    db.flush()\n    return group\n''',
)

write(
    "products/LoanHub/apps/backend/routers/employer_groups.py",
    '''from fastapi import APIRouter, Depends, Query\nfrom sqlalchemy import or_\nfrom sqlalchemy.orm import Session\n\nfrom database.models.employer_group import EmployerGroup\nfrom database.schemas.employer_group import EmployerGroupRead\nfrom database.session import get_db\n\n\nrouter = APIRouter(prefix="/employer-groups", tags=["Employer Groups"])\n\n\n@router.get("", response_model=list[EmployerGroupRead])\ndef list_employer_groups(\n    search: str | None = Query(default=None, max_length=120),\n    limit: int = Query(default=250, ge=1, le=500),\n    db: Session = Depends(get_db),\n):\n    query = db.query(EmployerGroup).filter(EmployerGroup.is_active.is_(True))\n    term = str(search or "").strip()\n    if term:\n        value = f"%{term}%"\n        query = query.filter(\n            or_(\n                EmployerGroup.code.ilike(value),\n                EmployerGroup.name.ilike(value),\n            )\n        )\n    return query.order_by(EmployerGroup.code.asc(), EmployerGroup.name.asc()).limit(limit).all()\n''',
)

# ---------------------------------------------------------------------------
# Migration: persistent catalog + borrower group/income-day fields + seed data.
# ---------------------------------------------------------------------------
write(
    "products/LoanHub/apps/backend/alembic/versions/a1b2c3d4e910_employer_groups_and_income_day.py",
    '''"""Employer groups and borrower income-day classification.\n\nRevision ID: a1b2c3d4e910\nRevises: z9n3p5q7r800\nCreate Date: 2026-09-08\n"""\n\nimport uuid\nfrom typing import Sequence, Union\n\nfrom alembic import op\nimport sqlalchemy as sa\nfrom sqlalchemy.dialects import postgresql\n\n\nrevision: str = "a1b2c3d4e910"\ndown_revision: Union[str, Sequence[str], None] = "z9n3p5q7r800"\nbranch_labels: Union[str, Sequence[str], None] = None\ndepends_on: Union[str, Sequence[str], None] = None\n\n\n_SEEDED_GROUPS = (\n    ("10000000-0000-0000-0000-000000000001", "L/GOV", "Lesotho Government"),\n    ("10000000-0000-0000-0000-000000000002", "LMPS", "Lesotho Mounted Police Service"),\n    ("10000000-0000-0000-0000-000000000003", "LCS", "Lesotho Correctional Service"),\n    ("10000000-0000-0000-0000-000000000004", "LDF", "Lesotho Defence Force"),\n    ("10000000-0000-0000-0000-000000000005", "NSS", "National Security Service"),\n    ("10000000-0000-0000-0000-000000000006", "NDSO", "NDSO"),\n    ("10000000-0000-0000-0000-000000000007", "PENSIONS", "Pensions"),\n    ("10000000-0000-0000-0000-000000000008", "NGO", "NGO"),\n    ("10000000-0000-0000-0000-000000000009", "LEMS", "LEMS"),\n    ("10000000-0000-0000-0000-000000000010", "LE HAE", "LE HAE"),\n)\n\n\ndef upgrade() -> None:\n    op.create_table(\n        "employer_groups",\n        sa.Column("code", sa.String(length=40), nullable=False),\n        sa.Column("name", sa.String(length=200), nullable=False),\n        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),\n        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),\n        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),\n        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),\n        sa.Column("created_by", sa.String(length=36), nullable=True),\n        sa.Column("updated_by", sa.String(length=36), nullable=True),\n        sa.PrimaryKeyConstraint("id"),\n        sa.UniqueConstraint("code", name="uq_employer_groups_code"),\n    )\n    op.create_index("ix_employer_groups_code", "employer_groups", ["code"], unique=False)\n    op.create_index("ix_employer_groups_name", "employer_groups", ["name"], unique=False)\n    op.create_index("ix_employer_groups_is_active", "employer_groups", ["is_active"], unique=False)\n\n    employer_groups = sa.table(\n        "employer_groups",\n        sa.column("id", postgresql.UUID(as_uuid=True)),\n        sa.column("code", sa.String()),\n        sa.column("name", sa.String()),\n        sa.column("is_active", sa.Boolean()),\n    )\n    op.bulk_insert(\n        employer_groups,\n        [\n            {"id": uuid.UUID(group_id), "code": code, "name": name, "is_active": True}\n            for group_id, code, name in _SEEDED_GROUPS\n        ],\n    )\n\n    op.add_column(\n        "borrowers",\n        sa.Column("employer_group_id", postgresql.UUID(as_uuid=True), nullable=True),\n    )\n    op.add_column(\n        "borrowers",\n        sa.Column("income_day", sa.Integer(), nullable=True),\n    )\n    op.create_foreign_key(\n        "fk_borrowers_employer_group_id",\n        "borrowers",\n        "employer_groups",\n        ["employer_group_id"],\n        ["id"],\n        ondelete="SET NULL",\n    )\n    op.create_index(\n        "ix_borrowers_employer_group_id",\n        "borrowers",\n        ["employer_group_id"],\n        unique=False,\n    )\n    op.create_check_constraint(\n        "ck_borrowers_income_day",\n        "borrowers",\n        "income_day IS NULL OR (income_day >= 1 AND income_day <= 31)",\n    )\n\n\ndef downgrade() -> None:\n    op.drop_constraint("ck_borrowers_income_day", "borrowers", type_="check")\n    op.drop_index("ix_borrowers_employer_group_id", table_name="borrowers")\n    op.drop_constraint("fk_borrowers_employer_group_id", "borrowers", type_="foreignkey")\n    op.drop_column("borrowers", "income_day")\n    op.drop_column("borrowers", "employer_group_id")\n    op.drop_index("ix_employer_groups_is_active", table_name="employer_groups")\n    op.drop_index("ix_employer_groups_name", table_name="employer_groups")\n    op.drop_index("ix_employer_groups_code", table_name="employer_groups")\n    op.drop_table("employer_groups")\n''',
)

# ---------------------------------------------------------------------------
# Backend model and schema integration.
# ---------------------------------------------------------------------------
replace_once(
    "products/LoanHub/apps/backend/database/models/borrower.py",
    "    employer_name = Column(String(200), nullable=True)\n    job_title = Column(String(150), nullable=True)\n",
    "    employer_name = Column(String(200), nullable=True)\n    employer_group_id = Column(\n        UUID(as_uuid=True),\n        ForeignKey(\"employer_groups.id\", ondelete=\"SET NULL\"),\n        nullable=True,\n        index=True,\n    )\n    income_day = Column(Integer, nullable=True)\n    job_title = Column(String(150), nullable=True)\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/models/borrower.py",
    "    user = relationship(\n        \"User\",\n        back_populates=\"borrower_profile\",\n    )\n\n",
    "    user = relationship(\n        \"User\",\n        back_populates=\"borrower_profile\",\n    )\n    employer_group = relationship(\n        \"EmployerGroup\",\n        back_populates=\"borrowers\",\n    )\n\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/models/__init__.py",
    "from database.models.employee import EmployeeProfile, PerformanceGoal, PerformanceReview\n",
    "from database.models.employee import EmployeeProfile, PerformanceGoal, PerformanceReview\nfrom database.models.employer_group import EmployerGroup\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/models/__init__.py",
    "    \"PerformanceReview\",\n",
    "    \"PerformanceReview\",\n    \"EmployerGroup\",\n",
)

replace_once(
    "products/LoanHub/apps/backend/database/schemas/borrower.py",
    "    employer_name: Optional[str] = None\n    job_title: Optional[str] = None\n",
    "    employer_name: Optional[str] = None\n    employer_group_id: Optional[UUID] = None\n    income_day: Optional[int] = Field(default=None, ge=1, le=31)\n    job_title: Optional[str] = None\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/schemas/borrower.py",
    "    employer_name: Optional[str] = None\n    job_title: Optional[str] = None\n    employment_start_date: Optional[date] = None\n",
    "    employer_name: Optional[str] = None\n    employer_group_id: Optional[UUID] = None\n    income_day: Optional[int] = Field(default=None, ge=1, le=31)\n    job_title: Optional[str] = None\n    employment_start_date: Optional[date] = None\n",
)

replace_once(
    "products/LoanHub/apps/backend/database/schemas/borrower_registration.py",
    "from pydantic import BaseModel, EmailStr\n",
    "from pydantic import BaseModel, EmailStr, Field\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/schemas/borrower_registration.py",
    "from database.models.enums import (\n",
    "from database.schemas.employer_group import EmployerGroupCreate\nfrom database.models.enums import (\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/schemas/borrower_registration.py",
    "    employer_name: Optional[str] = None\n    job_title: Optional[str] = None\n    monthly_income: Optional[Decimal] = None\n    salary_date: Optional[str] = None\n",
    "    employer_name: Optional[str] = None\n    employer_group_id: Optional[UUID] = None\n    new_employer_group: Optional[EmployerGroupCreate] = None\n    income_day: Optional[int] = Field(default=None, ge=1, le=31)\n    job_title: Optional[str] = None\n    monthly_income: Optional[Decimal] = None\n    salary_date: Optional[str] = None\n",
)

replace_once(
    "products/LoanHub/apps/backend/routers/borrower_registration.py",
    "from database.session import get_db\n",
    "from database.session import get_db\nfrom services.employer_group_service import resolve_employer_group\n",
)
replace_once(
    "products/LoanHub/apps/backend/routers/borrower_registration.py",
    "    try:\n        user = User(\n",
    "    try:\n        employer_group = resolve_employer_group(\n            db,\n            employer_group_id=payload.employer_group_id,\n            new_employer_group=payload.new_employer_group,\n        )\n\n        user = User(\n",
)
replace_once(
    "products/LoanHub/apps/backend/routers/borrower_registration.py",
    "            employer_name=clean_optional_string(\n                payload.employer_name,\n            ),\n            job_title=clean_optional_string(\n",
    "            employer_name=(\n                employer_group.name\n                if employer_group is not None\n                else clean_optional_string(payload.employer_name)\n            ),\n            employer_group_id=(employer_group.id if employer_group is not None else None),\n            income_day=payload.income_day,\n            job_title=clean_optional_string(\n",
)
replace_once(
    "products/LoanHub/apps/backend/routers/borrower_registration.py",
    "            salary_date=clean_optional_string(\n                payload.salary_date,\n            ),\n",
    "            salary_date=(\n                str(payload.income_day)\n                if payload.income_day is not None\n                else clean_optional_string(payload.salary_date)\n            ),\n",
)

# Company assisted registration payload/read contract.
replace_once(
    "products/LoanHub/apps/backend/database/schemas/company_clients.py",
    "from database.schemas.origination import BankAccountInput\n",
    "from database.schemas.origination import BankAccountInput\nfrom database.schemas.employer_group import EmployerGroupCreate\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/schemas/company_clients.py",
    "    employment_status: EmploymentStatus\n    employer_name: str | None = Field(default=None, max_length=200)\n    job_title: str | None = Field(default=None, max_length=150)\n    monthly_income: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)\n    salary_date: str | None = Field(default=None, max_length=20)\n",
    "    employment_status: EmploymentStatus\n    employer_name: str | None = Field(default=None, max_length=200)\n    employer_group_id: UUID | None = None\n    new_employer_group: EmployerGroupCreate | None = None\n    income_day: int | None = Field(default=None, ge=1, le=31)\n    job_title: str | None = Field(default=None, max_length=150)\n    monthly_income: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)\n    salary_date: str | None = Field(default=None, max_length=20)\n",
)
replace_once(
    "products/LoanHub/apps/backend/database/schemas/company_clients.py",
    "    employment_status: str\n    employer_name: str | None\n    job_title: str | None\n",
    "    employment_status: str\n    employer_name: str | None\n    employer_group_id: UUID | None = None\n    employer_group_code: str | None = None\n    income_day: int | None = None\n    job_title: str | None\n",
)

replace_once(
    "products/LoanHub/apps/backend/services/company_client_service.py",
    "from services.credential_service import encrypt_credential\n",
    "from services.credential_service import encrypt_credential\nfrom services.employer_group_service import resolve_employer_group\n",
)
replace_once(
    "products/LoanHub/apps/backend/services/company_client_service.py",
    "        borrower.consent_to_share_profile = bool(\n",
    "        employer_group = resolve_employer_group(\n            db,\n            employer_group_id=payload.employer_group_id,\n            new_employer_group=payload.new_employer_group,\n        )\n\n        borrower.consent_to_share_profile = bool(\n",
)
replace_once(
    "products/LoanHub/apps/backend/services/company_client_service.py",
    "        borrower.employment_status = payload.employment_status\n        borrower.employer_name = clean_optional(payload.employer_name)\n        borrower.job_title = clean_optional(payload.job_title)\n        borrower.monthly_income = payload.monthly_income\n        borrower.salary_date = clean_optional(payload.salary_date)\n",
    "        borrower.employment_status = payload.employment_status\n        borrower.employer_group_id = employer_group.id if employer_group is not None else None\n        borrower.employer_name = (\n            employer_group.name if employer_group is not None else clean_optional(payload.employer_name)\n        )\n        borrower.income_day = payload.income_day\n        borrower.job_title = clean_optional(payload.job_title)\n        borrower.monthly_income = payload.monthly_income\n        borrower.salary_date = (\n            str(payload.income_day) if payload.income_day is not None else clean_optional(payload.salary_date)\n        )\n",
)
replace_once(
    "products/LoanHub/apps/backend/services/company_client_service.py",
    "    try:\n        user = User(\n            email=email,\n",
    "    try:\n        employer_group = resolve_employer_group(\n            db,\n            employer_group_id=payload.employer_group_id,\n            new_employer_group=payload.new_employer_group,\n        )\n        user = User(\n            email=email,\n",
)
replace_once(
    "products/LoanHub/apps/backend/services/company_client_service.py",
    "            employment_status=payload.employment_status,\n            employer_name=clean_optional(payload.employer_name),\n            job_title=clean_optional(payload.job_title),\n            monthly_income=payload.monthly_income,\n            salary_date=clean_optional(payload.salary_date),\n",
    "            employment_status=payload.employment_status,\n            employer_group_id=employer_group.id if employer_group is not None else None,\n            employer_name=(\n                employer_group.name if employer_group is not None else clean_optional(payload.employer_name)\n            ),\n            income_day=payload.income_day,\n            job_title=clean_optional(payload.job_title),\n            monthly_income=payload.monthly_income,\n            salary_date=(\n                str(payload.income_day) if payload.income_day is not None else clean_optional(payload.salary_date)\n            ),\n",
)

replace_once(
    "products/LoanHub/apps/backend/routers/company_clients.py",
    "        employment_status=borrower.employment_status.value,\n        employer_name=borrower.employer_name,\n        job_title=borrower.job_title,\n",
    "        employment_status=borrower.employment_status.value,\n        employer_name=borrower.employer_name,\n        employer_group_id=borrower.employer_group_id,\n        employer_group_code=(borrower.employer_group.code if borrower.employer_group else None),\n        income_day=borrower.income_day,\n        job_title=borrower.job_title,\n",
)

# API composition.
replace_once(
    "products/LoanHub/apps/backend/api/v1/router.py",
    "    employees,\n    hrms,\n",
    "    employees,\n    employer_groups,\n    hrms,\n",
)
replace_once(
    "products/LoanHub/apps/backend/api/v1/router.py",
    "    borrower_registration.router,\n    mobile_onboarding.router,\n",
    "    borrower_registration.router,\n    employer_groups.router,\n    mobile_onboarding.router,\n",
)

# Focused backend unit tests for normalization rules.
write(
    "products/LoanHub/apps/backend/tests/test_employer_groups.py",
    '''import pytest\nfrom fastapi import HTTPException\n\nfrom services.employer_group_service import normalize_employer_group_code, normalize_employer_group_name\n\n\ndef test_employer_group_code_is_normalized_for_search_and_storage():\n    assert normalize_employer_group_code(" l/gov ") == "L/GOV"\n    assert normalize_employer_group_code("lMps") == "LMPS"\n    assert normalize_employer_group_code("le   hae") == "LE HAE"\n\n\ndef test_employer_group_code_rejects_unsupported_characters():\n    with pytest.raises(HTTPException):\n        normalize_employer_group_code("LCS#")\n\n\ndef test_employer_group_name_collapses_whitespace():\n    assert normalize_employer_group_name("  Lesotho   Government ") == "Lesotho Government"\n''',
)

# ---------------------------------------------------------------------------
# Frontend types/API/reusable searchable inline-add field.
# ---------------------------------------------------------------------------
write(
    "products/LoanHub/apps/frontend/types/employerGroup.ts",
    '''export type EmployerGroup = {\n  id: string;\n  code: string;\n  name: string;\n  is_active: boolean;\n  created_at: string;\n  updated_at: string;\n};\n\nexport type EmployerGroupCreate = {\n  code: string;\n  name: string;\n};\n''',
)

write(
    "products/LoanHub/apps/frontend/api/employerGroups.ts",
    '''import { api } from "@/lib/api";\nimport type { EmployerGroup } from "@/types/employerGroup";\n\nexport async function listEmployerGroups(search?: string): Promise<EmployerGroup[]> {\n  return (\n    await api.get<EmployerGroup[]>("/employer-groups", {\n      params: search?.trim() ? { search: search.trim() } : undefined,\n    })\n  ).data;\n}\n''',
)

write(
    "products/LoanHub/apps/frontend/components/clients/employer-group-registration-field.tsx",
    '''"use client";\n\nimport { useEffect, useMemo, useState } from "react";\nimport { Plus, X } from "lucide-react";\n\nimport { listEmployerGroups } from "@/api/employerGroups";\nimport { Button } from "@/components/ui/button";\nimport { Input } from "@/components/ui/input";\nimport { Label } from "@/components/ui/label";\nimport { SuggestionSearch } from "@/components/ui/suggestion-search";\nimport type { EmployerGroup, EmployerGroupCreate } from "@/types/employerGroup";\n\ntype Selection = {\n  employer_group_id: string | null;\n  employer_name: string | null;\n  new_employer_group: EmployerGroupCreate | null;\n};\n\ntype Props = {\n  employerGroupId?: string | null;\n  employerName?: string | null;\n  newEmployerGroup?: EmployerGroupCreate | null;\n  onChange: (selection: Selection) => void;\n  required?: boolean;\n};\n\nfunction display(group: Pick<EmployerGroup, "code" | "name">): string {\n  return `${group.code} — ${group.name}`;\n}\n\nexport function EmployerGroupRegistrationField({\n  employerGroupId,\n  employerName,\n  newEmployerGroup,\n  onChange,\n  required = false,\n}: Props) {\n  const [groups, setGroups] = useState<EmployerGroup[]>([]);\n  const [search, setSearch] = useState("");\n  const [adding, setAdding] = useState(false);\n  const [draftCode, setDraftCode] = useState("");\n  const [draftName, setDraftName] = useState("");\n  const [loadError, setLoadError] = useState<string | null>(null);\n\n  useEffect(() => {\n    let cancelled = false;\n    void listEmployerGroups()\n      .then((rows) => {\n        if (!cancelled) {\n          setGroups(rows);\n          setLoadError(null);\n        }\n      })\n      .catch(() => {\n        if (!cancelled) setLoadError("Employer groups could not be loaded. You can still add a new group below.");\n      });\n    return () => { cancelled = true; };\n  }, []);\n\n  const selected = useMemo(\n    () => groups.find((group) => group.id === employerGroupId) ?? null,\n    [employerGroupId, groups],\n  );\n\n  useEffect(() => {\n    if (selected) {\n      setSearch(display(selected));\n    } else if (newEmployerGroup) {\n      setSearch(`${newEmployerGroup.code} — ${newEmployerGroup.name}`);\n    } else if (employerName && !search) {\n      setSearch(employerName);\n    }\n  }, [employerName, newEmployerGroup, search, selected]);\n\n  const suggestions = useMemo(\n    () => groups.map((group) => ({\n      value: group.id,\n      label: `${group.code} — ${group.name}`,\n      description: group.name,\n      keywords: [group.code, group.name],\n    })),\n    [groups],\n  );\n\n  function clearSelection(nextSearch = "") {\n    setSearch(nextSearch);\n    onChange({\n      employer_group_id: null,\n      employer_name: nextSearch.trim() || null,\n      new_employer_group: null,\n    });\n  }\n\n  function saveDraft() {\n    const code = draftCode.trim().toUpperCase().replace(/\\s+/g, " ");\n    const name = draftName.trim().replace(/\\s+/g, " ");\n    if (!code || name.length < 2) return;\n    const existing = groups.find((group) => group.code.toUpperCase() === code);\n    if (existing) {\n      setSearch(display(existing));\n      setAdding(false);\n      onChange({\n        employer_group_id: existing.id,\n        employer_name: existing.name,\n        new_employer_group: null,\n      });\n      return;\n    }\n    setSearch(`${code} — ${name}`);\n    setAdding(false);\n    onChange({\n      employer_group_id: null,\n      employer_name: name,\n      new_employer_group: { code, name },\n    });\n  }\n\n  return (\n    <div className="space-y-2">\n      <div className="space-y-0.5">\n        <Label className="text-sm font-bold">\n          Employer / work group{required ? <span className="ml-1 text-destructive">*</span> : null}\n        </Label>\n        <p className="text-[11px] leading-4 text-muted-foreground">\n          Search by code or employer name. Add a new code here if it is not already listed.\n        </p>\n      </div>\n      <SuggestionSearch\n        value={search}\n        onValueChange={(value) => clearSelection(value)}\n        suggestions={suggestions}\n        placeholder="Search L/GOV, LMPS, LCS, LDF…"\n        emptyMessage="No matching employer/work group."\n        suggestionLabel="Employer / work groups"\n        maxSuggestions={12}\n        showSuggestionsOnFocus\n        onSuggestionSelect={(suggestion) => {\n          const group = groups.find((row) => row.id === suggestion.value);\n          if (!group) return;\n          setSearch(display(group));\n          setAdding(false);\n          onChange({\n            employer_group_id: group.id,\n            employer_name: group.name,\n            new_employer_group: null,\n          });\n        }}\n      />\n      {loadError ? <p className="text-xs text-amber-700 dark:text-amber-300">{loadError}</p> : null}\n      {newEmployerGroup ? (\n        <div className="flex items-center justify-between rounded-xl border bg-muted/30 px-3 py-2 text-xs">\n          <span><strong>{newEmployerGroup.code}</strong> · {newEmployerGroup.name} will be saved with this client.</span>\n          <Button type="button" variant="ghost" size="icon" className="h-7 w-7" onClick={() => clearSelection("")}>\n            <X className="h-3.5 w-3.5" />\n          </Button>\n        </div>\n      ) : null}\n      {!adding ? (\n        <Button\n          type="button"\n          variant="outline"\n          size="sm"\n          onClick={() => {\n            setDraftCode("");\n            setDraftName(search.includes("—") ? search.split("—").slice(1).join("—").trim() : search.trim());\n            setAdding(true);\n          }}\n        >\n          <Plus className="h-4 w-4" />Add new employer/group\n        </Button>\n      ) : (\n        <div className="rounded-2xl border bg-muted/20 p-3">\n          <div className="grid gap-3 sm:grid-cols-[140px_1fr]">\n            <div className="space-y-1">\n              <Label className="text-xs font-semibold">Group code</Label>\n              <Input value={draftCode} maxLength={40} onChange={(event) => setDraftCode(event.target.value)} placeholder="e.g. LMPS" />\n            </div>\n            <div className="space-y-1">\n              <Label className="text-xs font-semibold">Employer / group name</Label>\n              <Input value={draftName} maxLength={200} onChange={(event) => setDraftName(event.target.value)} placeholder="Employer or work group" />\n            </div>\n          </div>\n          <div className="mt-3 flex justify-end gap-2">\n            <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>Cancel</Button>\n            <Button type="button" size="sm" disabled={!draftCode.trim() || draftName.trim().length < 2} onClick={saveDraft}>\n              Use this group\n            </Button>\n          </div>\n        </div>\n      )}\n    </div>\n  );\n}\n''',
)

# Frontend borrower types.
replace_once(
    "products/LoanHub/apps/frontend/types/borrower.ts",
    "import type { UserRole } from \"@/types/auth\";\n",
    "import type { UserRole } from \"@/types/auth\";\nimport type { EmployerGroupCreate } from \"@/types/employerGroup\";\n",
)
replace_once(
    "products/LoanHub/apps/frontend/types/borrower.ts",
    "    employer_name: string | null;\n    job_title: string | null;\n",
    "    employer_name: string | null;\n    employer_group_id: string | null;\n    income_day: number | null;\n    job_title: string | null;\n",
)
replace_once(
    "products/LoanHub/apps/frontend/types/borrower.ts",
    "    employer_name: string;\n    job_title: string;\n    monthly_income: number;\n",
    "    employer_name: string;\n    employer_group_id: string | null;\n    new_employer_group: EmployerGroupCreate | null;\n    income_day: number | null;\n    job_title: string;\n    monthly_income: number;\n",
)
replace_once(
    "products/LoanHub/apps/frontend/types/borrower.ts",
    "    employer_name?: string | null;\n    job_title?: string | null;\n",
    "    employer_name?: string | null;\n    employer_group_id?: string | null;\n    income_day?: number | null;\n    job_title?: string | null;\n",
)

# Company client types.
replace_once(
    "products/LoanHub/apps/frontend/types/companyClient.ts",
    "import type { BankAccountInput } from \"@/types/origination\";\n",
    "import type { BankAccountInput } from \"@/types/origination\";\nimport type { EmployerGroupCreate } from \"@/types/employerGroup\";\n",
)
replace_once(
    "products/LoanHub/apps/frontend/types/companyClient.ts",
    "    employment_status: string;\n    employer_name: string | null;\n    job_title: string | null;\n",
    "    employment_status: string;\n    employer_name: string | null;\n    employer_group_id: string | null;\n    employer_group_code: string | null;\n    income_day: number | null;\n    job_title: string | null;\n",
)
replace_once(
    "products/LoanHub/apps/frontend/types/companyClient.ts",
    "    employment_status: \"employed\" | \"self_employed\" | \"unemployed\" | \"student\" | \"pensioner\";\n    employer_name?: string | null;\n    job_title?: string | null;\n    monthly_income?: number | null;\n    salary_date?: string | null;\n",
    "    employment_status: \"employed\" | \"self_employed\" | \"unemployed\" | \"student\" | \"pensioner\";\n    employer_name?: string | null;\n    employer_group_id?: string | null;\n    new_employer_group?: EmployerGroupCreate | null;\n    income_day?: number | null;\n    job_title?: string | null;\n    monthly_income?: number | null;\n    salary_date?: string | null;\n",
)

# Public borrower self-registration form.
replace_once(
    "products/LoanHub/apps/frontend/app/(visitors)/borrower-registration/_components/createBorrowerForm.tsx",
    "import { LoadingButton } from \"@/components/ui/loading-button\";\n",
    "import { LoadingButton } from \"@/components/ui/loading-button\";\nimport { EmployerGroupRegistrationField } from \"@/components/clients/employer-group-registration-field\";\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(visitors)/borrower-registration/_components/createBorrowerForm.tsx",
    "    employer_name: \"\",\n    job_title: \"\",\n    monthly_income: 0,\n    salary_date: \"\",\n",
    "    employer_name: \"\",\n    employer_group_id: null,\n    new_employer_group: null,\n    income_day: null,\n    job_title: \"\",\n    monthly_income: 0,\n    salary_date: \"\",\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(visitors)/borrower-registration/_components/createBorrowerForm.tsx",
    "        if (currentStep === 4) {\n",
    "        if (currentStep === 3) {\n            const needsIncomeDay = [\"employed\", \"self_employed\", \"pensioner\"].includes(form.employment_status);\n            const hasGroup = Boolean(form.employer_group_id || form.new_employer_group);\n            if (form.employment_status === \"employed\" && !hasGroup) {\n                setPasswordError(\"Select an employer/work group or add a new group.\");\n                return false;\n            }\n            if (needsIncomeDay && !form.income_day) {\n                setPasswordError(\"Enter the day of the month when you normally receive income.\");\n                return false;\n            }\n        }\n\n        if (currentStep === 4) {\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(visitors)/borrower-registration/_components/createBorrowerForm.tsx",
    "                            <Input label=\"Employer Name\" value={form.employer_name} onChange={(v) => updateField(\"employer_name\", v)} />\n                            <Input label=\"Job Title\" value={form.job_title} onChange={(v) => updateField(\"job_title\", v)} />\n",
    "                            <div className=\"sm:col-span-2\">\n                                <EmployerGroupRegistrationField\n                                    employerGroupId={form.employer_group_id}\n                                    employerName={form.employer_name}\n                                    newEmployerGroup={form.new_employer_group}\n                                    required={form.employment_status === \"employed\"}\n                                    onChange={(selection) => setForm((current) => ({ ...current, ...selection }))}\n                                />\n                            </div>\n                            <Input label=\"Job Title\" value={form.job_title} onChange={(v) => updateField(\"job_title\", v)} />\n                            <Input\n                                label=\"Income / pay day (1–31)\"\n                                type=\"number\"\n                                value={form.income_day ? String(form.income_day) : \"\"}\n                                onChange={(v) => updateField(\"income_day\", v ? Number(v) : null)}\n                                placeholder=\"e.g. 20\"\n                            />\n",
)

# Company-assisted client registration form.
replace_once(
    "products/LoanHub/apps/frontend/app/(dashboard)/company/clients/page.tsx",
    "import { CompanyClientProfileDialog } from \"@/components/clients/company-client-profile-dialog\";\n",
    "import { CompanyClientProfileDialog } from \"@/components/clients/company-client-profile-dialog\";\nimport { EmployerGroupRegistrationField } from \"@/components/clients/employer-group-registration-field\";\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(dashboard)/company/clients/page.tsx",
    "  employment_status: \"employed\",\n  employer_name: null,\n  job_title: null,\n  monthly_income: null,\n  salary_date: null,\n",
    "  employment_status: \"employed\",\n  employer_name: null,\n  employer_group_id: null,\n  new_employer_group: null,\n  income_day: null,\n  job_title: null,\n  monthly_income: null,\n  salary_date: null,\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(dashboard)/company/clients/page.tsx",
    "    if (step === 2) {\n      if (Number(clientForm.monthly_income ?? 0) < 0) errors.push(\"Monthly income cannot be negative.\");\n",
    "    if (step === 2) {\n      if (Number(clientForm.monthly_income ?? 0) < 0) errors.push(\"Monthly income cannot be negative.\");\n      const needsIncomeDay = [\"employed\", \"self_employed\", \"pensioner\"].includes(clientForm.employment_status);\n      if (clientForm.employment_status === \"employed\" && !clientForm.employer_group_id && !clientForm.new_employer_group) {\n        errors.push(\"Select the borrower’s employer/work group or add a new group.\");\n      }\n      if (needsIncomeDay && !clientForm.income_day) {\n        errors.push(\"Enter the borrower’s normal income/pay day (1–31).\");\n      }\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(dashboard)/company/clients/page.tsx",
    "        employer_name: optional(clientForm.employer_name),\n        job_title: optional(clientForm.job_title),\n        salary_date: optional(clientForm.salary_date),\n",
    "        employer_name: optional(clientForm.employer_name),\n        job_title: optional(clientForm.job_title),\n        salary_date: clientForm.income_day ? String(clientForm.income_day) : optional(clientForm.salary_date),\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(dashboard)/company/clients/page.tsx",
    "                        <Field label=\"Employer or business\">\n                          <Input className=\"h-11\" autoFocus value={clientForm.employer_name ?? \"\"} onChange={(event) => updateClient(\"employer_name\", event.target.value)} />\n                        </Field>\n                        <Field label=\"Job title\">\n",
    "                        <div className=\"md:col-span-2\">\n                          <EmployerGroupRegistrationField\n                            employerGroupId={clientForm.employer_group_id}\n                            employerName={clientForm.employer_name}\n                            newEmployerGroup={clientForm.new_employer_group}\n                            required={clientForm.employment_status === \"employed\"}\n                            onChange={(selection) => {\n                              setClientStepErrors([]);\n                              setClientForm((current) => ({ ...current, ...selection }));\n                            }}\n                          />\n                        </div>\n                        <Field label=\"Job title\">\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(dashboard)/company/clients/page.tsx",
    "                        <Field label=\"Monthly income\" description=\"Gross monthly income declared by the borrower.\">\n                          <Input className=\"h-11\" type=\"number\" min={0} step=\"0.01\" inputMode=\"decimal\" value={clientForm.monthly_income ?? \"\"} onChange={(event) => updateClient(\"monthly_income\", event.target.value ? Number(event.target.value) : null)} />\n                        </Field>\n",
    "                        <Field label=\"Monthly income\" description=\"Gross monthly income declared by the borrower.\">\n                          <Input className=\"h-11\" type=\"number\" min={0} step=\"0.01\" inputMode=\"decimal\" value={clientForm.monthly_income ?? \"\"} onChange={(event) => updateClient(\"monthly_income\", event.target.value ? Number(event.target.value) : null)} />\n                        </Field>\n                        <Field label=\"Income / pay day\" description=\"Day of the month the borrower normally receives income, for example 20 for the 20th.\">\n                          <Input className=\"h-11\" type=\"number\" min={1} max={31} inputMode=\"numeric\" value={clientForm.income_day ?? \"\"} onChange={(event) => updateClient(\"income_day\", event.target.value ? Number(event.target.value) : null)} placeholder=\"1–31\" />\n                        </Field>\n",
)
replace_once(
    "products/LoanHub/apps/frontend/app/(dashboard)/company/clients/page.tsx",
    "                            <ReviewItem label=\"Employer\" value={clientForm.employer_name || \"Not supplied\"} />\n                            <ReviewItem label=\"Monthly income\" value={clientForm.monthly_income !== null ? formatMoney(clientForm.monthly_income) : \"Not supplied\"} />\n",
    "                            <ReviewItem label=\"Employer / work group\" value={clientForm.new_employer_group ? `${clientForm.new_employer_group.code} — ${clientForm.new_employer_group.name}` : (clientForm.employer_name || \"Not supplied\")} />\n                            <ReviewItem label=\"Income / pay day\" value={clientForm.income_day ? `Day ${clientForm.income_day} of each month` : \"Not supplied\"} />\n                            <ReviewItem label=\"Monthly income\" value={clientForm.monthly_income !== null ? formatMoney(clientForm.monthly_income) : \"Not supplied\"} />\n",
)

print("LoanHub employer-group/pay-day branch patch applied successfully.")
