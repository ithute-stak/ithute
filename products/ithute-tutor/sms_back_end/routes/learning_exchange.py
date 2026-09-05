from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from database.multi_tenant_school_management.models import (
    Grade,
    LearningMaterial,
    LearningMaterialApproval,
    Subject,
    User,
)
from database.session import get_db
from utils.auth.tokens import get_current_user
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/learning", tags=["Cross-school Learning Exchange"])

MATERIAL_AUTHORS = (
    "school_admin",
    "principal",
    "vice_principal",
    "teacher",
    "class_teacher",
)
PEER_APPROVERS = ("school_admin", "principal", "vice_principal")


class LearningMaterialPayload(BaseModel):
    title: str = Field(min_length=2, max_length=220)
    description: str | None = Field(default=None, max_length=1000)
    content_type: Literal["note", "document", "link", "video", "worksheet", "lesson", "other"] = "note"
    body: str | None = None
    resource_url: HttpUrl | None = None
    grade_id: UUID | None = None
    subject_id: UUID | None = None
    visibility: Literal["school", "public"] = "school"
    peer_approval_threshold: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def validate_content(self):
        if not (self.body and self.body.strip()) and self.resource_url is None:
            raise ValueError("Provide material body or a resource URL")
        return self


class PlatformModeration(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)


class PeerApprovalPayload(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _role(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


def _load_material(db: Session, material_id: UUID) -> LearningMaterial:
    item = (
        db.query(LearningMaterial)
        .options(
            joinedload(LearningMaterial.school),
            joinedload(LearningMaterial.grade),
            joinedload(LearningMaterial.subject),
            joinedload(LearningMaterial.approvals).joinedload(LearningMaterialApproval.school),
        )
        .filter(LearningMaterial.id == material_id)
        .first()
    )
    if item is None:
        raise HTTPException(404, "Learning material not found")
    return item


def _validate_catalog(db: Session, grade_id: UUID | None, subject_id: UUID | None) -> None:
    if grade_id is not None and db.get(Grade, grade_id) is None:
        raise HTTPException(404, "Grade not found in the Tutor catalog")
    if subject_id is not None and db.get(Subject, subject_id) is None:
        raise HTTPException(404, "Subject not found in the Tutor catalog")


def _serialize(item: LearningMaterial) -> dict:
    approvals = sorted(item.approvals or [], key=lambda row: row.approved_at or datetime.min)
    return {
        "id": str(item.id),
        "school_id": str(item.school_id),
        "source_school": item.school.name if item.school else None,
        "author_user_id": str(item.author_user_id) if item.author_user_id else None,
        "title": item.title,
        "description": item.description,
        "content_type": item.content_type,
        "body": item.body,
        "resource_url": item.resource_url,
        "grade_id": str(item.grade_id) if item.grade_id else None,
        "grade": item.grade.name if item.grade else None,
        "subject_id": str(item.subject_id) if item.subject_id else None,
        "subject": item.subject.name if item.subject else None,
        "visibility": item.visibility,
        "moderation_status": item.moderation_status,
        "approval_source": item.approval_source,
        "peer_approval_threshold": item.peer_approval_threshold,
        "peer_approval_count": len(approvals),
        "peer_approvals": [
            {
                "school_id": str(approval.school_id),
                "school": approval.school.name if approval.school else None,
                "approved_at": approval.approved_at.isoformat() if approval.approved_at else None,
                "note": approval.note,
            }
            for approval in approvals
        ],
        "platform_moderation_note": item.platform_moderation_note,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _reset_public_approval(db: Session, item: LearningMaterial) -> None:
    # Approved content cannot be silently changed while retaining approval.
    db.query(LearningMaterialApproval).filter(
        LearningMaterialApproval.material_id == item.id
    ).delete(synchronize_session=False)
    item.moderation_status = "draft"
    item.approval_source = None
    item.platform_moderated_by = None
    item.platform_moderation_note = None
    item.platform_moderated_at = None
    item.published_at = None


@router.post("/materials", status_code=201)
def create_learning_material(
    payload: LearningMaterialPayload,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MATERIAL_AUTHORS)),
):
    _validate_catalog(db, payload.grade_id, payload.subject_id)
    values = payload.model_dump()
    if values.get("resource_url") is not None:
        values["resource_url"] = str(values["resource_url"])
    item = LearningMaterial(
        school_id=context.school_id,
        author_user_id=context.user_id,
        moderation_status="draft",
        **values,
    )
    db.add(item)
    db.commit()
    return _serialize(_load_material(db, item.id))


@router.get("/materials/mine")
def list_school_learning_materials(
    include_archived: bool = False,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(LearningMaterial).filter(LearningMaterial.school_id == context.school_id)
    if not include_archived:
        query = query.filter(LearningMaterial.moderation_status != "archived", LearningMaterial.is_active.is_(True))
    rows = query.order_by(LearningMaterial.updated_at.desc()).all()
    return [_serialize(_load_material(db, row.id)) for row in rows]


@router.get("/library")
def shared_learning_library(
    grade_id: UUID | None = None,
    subject_id: UUID | None = None,
    source_school_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    # Any authenticated school member, including students, can consume only
    # public content that passed Tutor platform or independent peer-school approval.
    query = db.query(LearningMaterial).filter(
        LearningMaterial.visibility == "public",
        LearningMaterial.moderation_status == "approved",
        LearningMaterial.is_active.is_(True),
    )
    if grade_id:
        query = query.filter(LearningMaterial.grade_id == grade_id)
    if subject_id:
        query = query.filter(LearningMaterial.subject_id == subject_id)
    if source_school_id:
        query = query.filter(LearningMaterial.school_id == source_school_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(or_(LearningMaterial.title.ilike(pattern), LearningMaterial.description.ilike(pattern)))
    rows = query.order_by(LearningMaterial.published_at.desc(), LearningMaterial.created_at.desc()).limit(500).all()
    return [_serialize(_load_material(db, row.id)) for row in rows]


@router.get("/materials/{material_id}")
def get_learning_material(
    material_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    item = _load_material(db, material_id)
    is_owner = item.school_id == context.school_id
    is_shared = item.visibility == "public" and item.moderation_status == "approved" and item.is_active
    if not (is_owner or is_shared or context.is_platform_admin):
        raise HTTPException(404, "Learning material not available in this school")
    return _serialize(item)


@router.put("/materials/{material_id}")
def update_learning_material(
    material_id: UUID,
    payload: LearningMaterialPayload,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MATERIAL_AUTHORS)),
):
    item = _load_material(db, material_id)
    if item.school_id != context.school_id:
        raise HTTPException(403, "Only the owning school can edit this material")
    if item.moderation_status == "archived":
        raise HTTPException(409, "Archived material cannot be edited")
    _validate_catalog(db, payload.grade_id, payload.subject_id)
    values = payload.model_dump()
    if values.get("resource_url") is not None:
        values["resource_url"] = str(values["resource_url"])
    for key, value in values.items():
        setattr(item, key, value)
    _reset_public_approval(db, item)
    db.commit()
    return _serialize(_load_material(db, item.id))


@router.post("/materials/{material_id}/submit")
def submit_learning_material(
    material_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MATERIAL_AUTHORS)),
):
    item = _load_material(db, material_id)
    if item.school_id != context.school_id:
        raise HTTPException(403, "Only the owning school can submit this material")
    if item.visibility != "public":
        raise HTTPException(400, "Set visibility to public before submitting for cross-school approval")
    if item.moderation_status == "archived":
        raise HTTPException(409, "Archived material cannot be submitted")
    _reset_public_approval(db, item)
    item.moderation_status = "pending"
    db.commit()
    return _serialize(_load_material(db, item.id))


@router.post("/materials/{material_id}/peer-approve")
def peer_approve_learning_material(
    material_id: UUID,
    payload: PeerApprovalPayload,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*PEER_APPROVERS)),
):
    if context.is_platform_admin:
        raise HTTPException(400, "Platform administration must use !thute Tutor platform moderation")
    item = _load_material(db, material_id)
    if item.school_id == context.school_id:
        raise HTTPException(400, "The publishing school cannot approve its own public material")
    if not item.is_active or item.visibility != "public" or item.moderation_status != "pending":
        raise HTTPException(409, "Material is not awaiting peer-school approval")
    existing = db.query(LearningMaterialApproval).filter(
        LearningMaterialApproval.material_id == item.id,
        LearningMaterialApproval.school_id == context.school_id,
    ).first()
    if existing:
        raise HTTPException(409, "This school has already approved the material")

    db.add(LearningMaterialApproval(
        material_id=item.id,
        school_id=context.school_id,
        approved_by=context.user_id,
        note=payload.note,
    ))
    db.flush()
    count = db.query(LearningMaterialApproval).filter(
        LearningMaterialApproval.material_id == item.id
    ).count()
    if count >= item.peer_approval_threshold:
        item.moderation_status = "approved"
        item.approval_source = "peer"
        item.published_at = _utcnow()
    db.commit()
    return _serialize(_load_material(db, item.id))


@router.post("/materials/{material_id}/platform-moderate")
def platform_moderate_learning_material(
    material_id: UUID,
    payload: PlatformModeration,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if _role(user) != "super_admin":
        raise HTTPException(403, "Only !thute Tutor platform administration can perform platform moderation")
    item = _load_material(db, material_id)
    if item.visibility != "public" or item.moderation_status not in {"pending", "approved"}:
        raise HTTPException(409, "Material is not available for platform moderation")

    item.platform_moderated_by = user.id
    item.platform_moderation_note = payload.note
    item.platform_moderated_at = _utcnow()
    if payload.decision == "approved":
        item.moderation_status = "approved"
        item.approval_source = "platform"
        item.published_at = _utcnow()
    else:
        db.query(LearningMaterialApproval).filter(
            LearningMaterialApproval.material_id == item.id
        ).delete(synchronize_session=False)
        item.moderation_status = "rejected"
        item.approval_source = None
        item.published_at = None
    db.commit()
    return _serialize(_load_material(db, item.id))


@router.post("/materials/{material_id}/archive")
def archive_learning_material(
    material_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*MATERIAL_AUTHORS)),
):
    item = _load_material(db, material_id)
    if item.school_id != context.school_id:
        raise HTTPException(403, "Only the owning school can archive this material")
    item.is_active = False
    item.moderation_status = "archived"
    item.published_at = None
    db.commit()
    return {"message": "Learning material archived", "id": str(item.id)}
