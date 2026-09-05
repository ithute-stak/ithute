from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import ParentStudent, StudentEnrollment
from database.multi_tenant_school_management.models.tutor_completion import Assignment, MasteryRecord, QuestionBankItem, StudyPlan
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context

router = APIRouter(prefix="/tutor", tags=["Personal Tutor"])
LEARNING_STAFF = {"school_admin", "principal", "vice_principal", "teacher", "class_teacher"}


def _can_view_learner(db: Session, context: SchoolContext, student_id: UUID) -> bool:
    if context.is_platform_admin or context.role in LEARNING_STAFF:
        return db.query(StudentEnrollment).filter(
            StudentEnrollment.school_id == context.school_id,
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.is_current.is_(True),
        ).first() is not None
    if context.role == "student":
        return context.user_id == student_id
    if context.role == "parent":
        return db.query(ParentStudent).filter(
            ParentStudent.parent_id == context.user_id,
            ParentStudent.student_id == student_id,
        ).first() is not None
    return False


def _profile(db: Session, context: SchoolContext, student_id: UUID):
    if not _can_view_learner(db, context, student_id):
        raise HTTPException(status_code=403, detail="learner is not available in this workspace")
    enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    # Mastery is intentionally longitudinal: it follows the same learner identity
    # across schools. School authorization above gates access to the learner.
    mastery = db.query(MasteryRecord).filter(MasteryRecord.student_id == student_id).all()
    topic_best: dict[tuple[str, str], MasteryRecord] = {}
    for record in mastery:
        key = (str(record.subject_id), record.topic_key)
        current = topic_best.get(key)
        if current is None or float(record.mastery_score or 0) > float(current.mastery_score or 0):
            topic_best[key] = record
    ordered = sorted(topic_best.values(), key=lambda item: float(item.mastery_score or 0))
    assignments = []
    if enrollment and enrollment.class_id:
        assignments = db.query(Assignment).filter(
            Assignment.school_id == context.school_id,
            Assignment.class_id == enrollment.class_id,
            Assignment.status == "published",
        ).order_by(Assignment.due_at.asc().nullslast()).limit(20).all()
    weak = [record for record in ordered if float(record.mastery_score or 0) < 70]
    return enrollment, ordered, assignments, weak


@router.get("/me")
def my_tutor(db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    if context.role != "student":
        raise HTTPException(status_code=403, detail="personal Tutor is a learner experience")
    return learner_tutor(context.user_id, db, context)


@router.get("/students/{student_id}")
def learner_tutor(student_id: UUID, db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    enrollment, mastery, assignments, weak = _profile(db, context, student_id)
    return {
        "student_id": student_id,
        "current_school_id": context.school_id,
        "current_class_id": enrollment.class_id if enrollment else None,
        "mastery": mastery,
        "weak_topics": weak,
        "assignments": assignments,
        "recommended_modes": [
            {"mode": "revise", "reason": "Start with the lowest mastery topics."} if weak else {"mode": "practice", "reason": "Maintain current mastery with mixed practice."},
            {"mode": "homework", "reason": "Work through current school assignments."},
            {"mode": "quiz", "reason": "Use question-bank practice to produce new mastery evidence."},
        ],
    }


@router.post("/students/{student_id}/study-plan/auto")
def auto_study_plan(student_id: UUID, db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    enrollment, mastery, assignments, weak = _profile(db, context, student_id)
    items = []
    for record in weak[:8]:
        items.append({
            "kind": "mastery",
            "subject_id": str(record.subject_id),
            "topic": record.topic_key,
            "current_mastery": float(record.mastery_score or 0),
            "target_mastery": 80,
            "action": "Revise the topic, work examples, then complete a short quiz.",
        })
    for assignment in assignments[:5]:
        items.append({
            "kind": "assignment",
            "assignment_id": str(assignment.id),
            "title": assignment.title,
            "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
            "action": "Complete and submit before the deadline.",
        })
    plan = StudyPlan(
        school_id=context.school_id,
        student_id=student_id,
        title=f"Personal study plan — {datetime.now(timezone.utc).date().isoformat()}",
        reason="Generated from longitudinal mastery and current school assignments.",
        items=items,
        status="active",
    )
    db.add(plan); db.commit(); db.refresh(plan); return plan


@router.get("/students/{student_id}/practice")
def practice_questions(
    student_id: UUID,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    _, mastery, _, weak = _profile(db, context, student_id)
    weak_keys = {(record.subject_id, record.topic_key) for record in weak}
    query = db.query(QuestionBankItem).filter(
        QuestionBankItem.school_id == context.school_id,
        QuestionBankItem.status == "active",
    )
    questions = query.order_by(QuestionBankItem.created_at.desc()).limit(200).all()
    selected = [q for q in questions if (q.subject_id, q.topic_key) in weak_keys][:limit]
    if not selected:
        selected = questions[:limit]
    return [
        {
            "id": q.id,
            "subject_id": q.subject_id,
            "topic_key": q.topic_key,
            "prompt": q.prompt,
            "question_type": q.question_type,
            "choices": q.choices,
            "points": q.points,
        }
        for q in selected
    ]
