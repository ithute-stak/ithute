from uuid import UUID
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# =========================
# BASE
# =========================

class ClassBase(BaseModel):
    name: str              # A, B, C
    grade_id: UUID


# =========================
# CREATE
# =========================

class ClassCreate(ClassBase):
    pass


# =========================
# UPDATE
# =========================

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    grade_id: Optional[UUID] = None


# =========================
# SIMPLE MODELS (RELATIONS)
# =========================

class GradeSimple(BaseModel):
    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class StudentSimple(BaseModel):
    id: UUID
    admission_number: str

    model_config = ConfigDict(from_attributes=True)


# =========================
# RESPONSE
# =========================

class ClassResponse(ClassBase):
    id: UUID

    # ✅ FIXED: datetime instead of string
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# =========================
# DETAILED RESPONSE
# =========================

class ClassDetailResponse(ClassResponse):
    """
    Use when returning class with relationships
    """

    # ✅ Avoid dicts → use typed models
    grade: Optional[GradeSimple] = None

    # ✅ FIXED: no [] default + typed
    students: Optional[List[StudentSimple]] = None

    model_config = ConfigDict(from_attributes=True)