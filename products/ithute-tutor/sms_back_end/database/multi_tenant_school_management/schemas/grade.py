from uuid import UUID
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# =========================
# BASE
# =========================

class GradeBase(BaseModel):
    name: str


# =========================
# CREATE
# =========================

class GradeCreate(GradeBase):
    pass


# =========================
# UPDATE
# =========================

class GradeUpdate(BaseModel):
    name: Optional[str] = None


# =========================
# SIMPLE CLASS (for relations)
# =========================

class ClassSimple(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


# =========================
# RESPONSE
# =========================

class GradeResponse(GradeBase):
    id: UUID

    # ✅ FIXED: use datetime instead of string
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# =========================
# DETAILED RESPONSE
# =========================

class GradeDetailResponse(GradeResponse):
    """
    Use when returning grade with relationships
    """

    # Avoid raw dicts — use typed models
    school: Optional[dict] = None

    # ✅ FIXED: no mutable default + proper typing
    classes: Optional[List[ClassSimple]] = None

    model_config = ConfigDict(from_attributes=True)