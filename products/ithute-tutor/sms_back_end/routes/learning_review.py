from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import LearningMaterial, LearningMaterialApproval, User
from database.session import get_db
from routes.learning_exchange import PEER_APPROVERS, _load_material, _role, _serialize
from utils.auth.tokens import get_current_user
from utils.school_context import SchoolContext, require_school_roles

router = APIRouter(prefix="/learning", tags=["Cross-school Learning Review"])


@router.get("/review-queue")
def peer_school_review_queue(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*PEER_APPROVERS)),
):
    if context.is_platform_admin:
        raise HTTPException(403, "Platform administration must use the !thute Tutor review queue")
    rows = db.query(LearningMaterial).filter(
        LearningMaterial.school_id != context.school_id,
        LearningMaterial.visibility == "public",
        LearningMaterial.moderation_status == "pending",
        LearningMaterial.is_active.is_(True),
        ~LearningMaterial.approvals.any(LearningMaterialApproval.school_id == context.school_id),
    ).order_by(LearningMaterial.created_at.asc()).limit(300).all()
    return [_serialize(_load_material(db, row.id)) for row in rows]


@router.get("/platform-review-queue")
def platform_review_queue(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if _role(user) != "super_admin":
        raise HTTPException(403, "Only !thute Tutor platform administration can view the platform review queue")
    rows = db.query(LearningMaterial).filter(
        LearningMaterial.visibility == "public",
        LearningMaterial.moderation_status == "pending",
        LearningMaterial.is_active.is_(True),
    ).order_by(LearningMaterial.created_at.asc()).limit(500).all()
    return [_serialize(_load_material(db, row.id)) for row in rows]
