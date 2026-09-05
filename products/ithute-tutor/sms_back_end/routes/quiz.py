from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import StudentEnrollment, Teacher
from database.multi_tenant_school_management.models.academic_core import Assessment, AssessmentResult
from database.multi_tenant_school_management.models.tutor_assessment import QuizAttempt, QuizResponse
from database.multi_tenant_school_management.models.tutor_completion import MasteryRecord, QuestionBankItem
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles
from utils.tutor_notifications import notify_user

router = APIRouter(prefix="/quiz", tags=["Online Assessment"])
ASSESSMENT_STAFF = ("school_admin", "principal", "vice_principal", "teacher", "class_teacher")
MANAGEMENT_ROLES = {"school_admin", "principal", "vice_principal"}


class AttemptSubmission(BaseModel):
    responses: dict[str, object | None] = Field(default_factory=dict)


class ManualMark(BaseModel):
    awarded_points: Decimal = Field(ge=0)


class QuizQuestionCreate(BaseModel):
    topic_key: str | None = Field(default=None, max_length=160)
    prompt: str = Field(min_length=2)
    question_type: Literal["multiple_choice", "true_false", "short_answer", "long_answer"] = "short_answer"
    choices: list[str] | None = None
    correct_answer: object | None = None
    points: Decimal = Field(default=Decimal("1"), gt=0)
    explanation: str | None = None


def _student_can_take(db: Session, context: SchoolContext, assessment: Assessment) -> bool:
    if context.role != "student":
        return False
    return db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.student_id == context.user_id,
        StudentEnrollment.class_id == assessment.class_id,
        StudentEnrollment.is_current.is_(True),
    ).first() is not None


def _teacher_profile_id(db: Session, context: SchoolContext) -> UUID | None:
    if context.role not in {"teacher", "class_teacher"}:
        return None
    teacher = db.query(Teacher).filter(
        Teacher.school_id == context.school_id,
        Teacher.user_id == context.user_id,
    ).first()
    return teacher.id if teacher else None


def _assert_can_manage_assessment(db: Session, context: SchoolContext, assessment: Assessment) -> None:
    if context.is_platform_admin or context.role in MANAGEMENT_ROLES:
        return
    teacher_id = _teacher_profile_id(db, context)
    if not teacher_id or assessment.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="assessment is not assigned to this teacher")


def _question_total(db: Session, school_id: UUID, assessment_id: UUID) -> Decimal:
    value = db.query(func.coalesce(func.sum(QuestionBankItem.points), 0)).filter(
        QuestionBankItem.school_id == school_id,
        QuestionBankItem.assessment_id == assessment_id,
        QuestionBankItem.status == "active",
    ).scalar()
    return Decimal(str(value or 0))


def _safe_question(question: QuestionBankItem):
    return {
        "id": question.id,
        "topic_key": question.topic_key,
        "prompt": question.prompt,
        "question_type": question.question_type,
        "choices": question.choices,
        "points": question.points,
    }


def _normalise(value):
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, list):
        return sorted(_normalise(item) for item in value)
    return value


def _record_mastery(
    db: Session,
    *,
    school_id: UUID,
    student_id: UUID,
    question: QuestionBankItem,
    awarded: Decimal,
    evidence: str,
) -> None:
    if not question.topic_key:
        return
    points = Decimal(str(question.points or 0))
    percent = Decimal("0") if points <= 0 else max(Decimal("0"), min(Decimal("100"), awarded / points * Decimal("100")))
    mastery = db.query(MasteryRecord).filter(
        MasteryRecord.school_id == school_id,
        MasteryRecord.student_id == student_id,
        MasteryRecord.subject_id == question.subject_id,
        MasteryRecord.topic_key == question.topic_key,
    ).first()
    if not mastery:
        mastery = MasteryRecord(
            school_id=school_id,
            student_id=student_id,
            subject_id=question.subject_id,
            topic_key=question.topic_key,
            mastery_score=percent,
            evidence_count=0,
        )
        db.add(mastery)
    else:
        old_count = mastery.evidence_count or 0
        old_score = Decimal(str(mastery.mastery_score or 0))
        mastery.mastery_score = ((old_score * old_count) + percent) / Decimal(str(old_count + 1))
    mastery.evidence_count = (mastery.evidence_count or 0) + 1
    mastery.last_evidence = evidence
    mastery.last_evidence_at = datetime.now(timezone.utc)


def _sync_assessment_result(db: Session, *, attempt: QuizAttempt) -> AssessmentResult:
    result = db.query(AssessmentResult).filter(
        AssessmentResult.assessment_id == attempt.assessment_id,
        AssessmentResult.student_id == attempt.student_id,
    ).first()
    if not result:
        result = AssessmentResult(
            school_id=attempt.school_id,
            assessment_id=attempt.assessment_id,
            student_id=attempt.student_id,
        )
        db.add(result)
    result.score = attempt.score
    result.is_absent = False
    result.is_excused = False
    return result


@router.get("/available")
def available_quizzes(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    if context.role != "student":
        raise HTTPException(status_code=403, detail="available quizzes are a learner view")
    enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.student_id == context.user_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    if not enrollment or enrollment.class_id is None:
        return []
    assessments = db.query(Assessment).filter(
        Assessment.school_id == context.school_id,
        Assessment.class_id == enrollment.class_id,
        Assessment.is_published.is_(True),
        Assessment.assessment_type.in_(["quiz", "test", "exam"]),
    ).order_by(Assessment.assessment_date.desc(), Assessment.created_at.desc()).all()
    result = []
    for assessment in assessments:
        question_count = db.query(QuestionBankItem).filter(
            QuestionBankItem.school_id == context.school_id,
            QuestionBankItem.assessment_id == assessment.id,
            QuestionBankItem.status == "active",
        ).count()
        if question_count == 0 or _question_total(db, context.school_id, assessment.id) != Decimal(str(assessment.max_score)):
            continue
        latest = db.query(QuizAttempt).filter(
            QuizAttempt.assessment_id == assessment.id,
            QuizAttempt.student_id == context.user_id,
        ).order_by(QuizAttempt.created_at.desc()).first()
        result.append({
            "id": assessment.id,
            "title": assessment.title,
            "assessment_type": assessment.assessment_type,
            "assessment_date": assessment.assessment_date,
            "max_score": assessment.max_score,
            "question_count": question_count,
            "attempt": latest,
        })
    return result


@router.get("/assessments/{assessment_id}")
def get_quiz(
    assessment_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.school_id == context.school_id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="assessment not found")
    if context.role == "student":
        if not assessment.is_published or not _student_can_take(db, context, assessment):
            raise HTTPException(status_code=403, detail="assessment is not available to this learner")
    elif context.is_platform_admin or context.role in ASSESSMENT_STAFF:
        if context.role in {"teacher", "class_teacher"}:
            _assert_can_manage_assessment(db, context, assessment)
    else:
        raise HTTPException(status_code=403, detail="not permitted to view this online assessment")
    questions = db.query(QuestionBankItem).filter(
        QuestionBankItem.school_id == context.school_id,
        QuestionBankItem.assessment_id == assessment_id,
        QuestionBankItem.status == "active",
    ).order_by(QuestionBankItem.created_at.asc()).all()
    return {
        "assessment": {
            "id": assessment.id,
            "title": assessment.title,
            "assessment_type": assessment.assessment_type,
            "max_score": assessment.max_score,
        },
        "questions": [_safe_question(item) for item in questions],
    }


@router.post("/assessments/{assessment_id}/questions")
def add_quiz_question(
    assessment_id: UUID,
    payload: QuizQuestionCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ASSESSMENT_STAFF)),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.school_id == context.school_id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="assessment not found")
    _assert_can_manage_assessment(db, context, assessment)
    if db.query(QuizAttempt).filter(QuizAttempt.assessment_id == assessment_id).first():
        raise HTTPException(status_code=409, detail="questions cannot change after learner attempts have started")
    if payload.question_type == "multiple_choice" and (not payload.choices or len(payload.choices) < 2):
        raise HTTPException(status_code=422, detail="multiple choice questions require at least two choices")
    if payload.question_type in {"multiple_choice", "true_false", "short_answer"} and payload.correct_answer is None:
        raise HTTPException(status_code=422, detail="auto-marked questions require a correct answer")
    projected = _question_total(db, context.school_id, assessment_id) + payload.points
    if projected > Decimal(str(assessment.max_score)):
        raise HTTPException(status_code=422, detail="question points would exceed the assessment maximum score")
    question = QuestionBankItem(
        school_id=context.school_id,
        subject_id=assessment.subject_id,
        class_id=assessment.class_id,
        assessment_id=assessment.id,
        **payload.model_dump(),
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.get("/assessments/{assessment_id}/attempts")
def assessment_attempts(
    assessment_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ASSESSMENT_STAFF)),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.school_id == context.school_id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="assessment not found")
    _assert_can_manage_assessment(db, context, assessment)
    questions = {
        item.id: item
        for item in db.query(QuestionBankItem).filter(
            QuestionBankItem.school_id == context.school_id,
            QuestionBankItem.assessment_id == assessment_id,
        ).all()
    }
    attempts = db.query(QuizAttempt).filter(
        QuizAttempt.school_id == context.school_id,
        QuizAttempt.assessment_id == assessment_id,
    ).order_by(QuizAttempt.submitted_at.desc().nullslast(), QuizAttempt.created_at.desc()).all()
    payload = []
    for attempt in attempts:
        responses = db.query(QuizResponse).filter(QuizResponse.attempt_id == attempt.id).all()
        payload.append({
            "id": attempt.id,
            "student_id": attempt.student_id,
            "status": attempt.status,
            "started_at": attempt.started_at,
            "submitted_at": attempt.submitted_at,
            "score": attempt.score,
            "max_score": attempt.max_score,
            "responses": [
                {
                    "id": response.id,
                    "question_id": response.question_id,
                    "prompt": questions.get(response.question_id).prompt if questions.get(response.question_id) else "Question",
                    "question_type": questions.get(response.question_id).question_type if questions.get(response.question_id) else "unknown",
                    "points": questions.get(response.question_id).points if questions.get(response.question_id) else None,
                    "answer": response.answer,
                    "is_correct": response.is_correct,
                    "awarded_points": response.awarded_points,
                }
                for response in responses
            ],
        })
    return payload


@router.post("/assessments/{assessment_id}/attempts")
def start_attempt(
    assessment_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.school_id == context.school_id,
        Assessment.is_published.is_(True),
    ).first()
    if not assessment or not _student_can_take(db, context, assessment):
        raise HTTPException(status_code=403, detail="assessment is not available to this learner")
    if _question_total(db, context.school_id, assessment_id) != Decimal(str(assessment.max_score)):
        raise HTTPException(status_code=409, detail="online assessment is not fully configured for its maximum score")
    active = db.query(QuizAttempt).filter(
        QuizAttempt.assessment_id == assessment_id,
        QuizAttempt.student_id == context.user_id,
        QuizAttempt.status == "in_progress",
    ).first()
    if active:
        return active
    completed = db.query(QuizAttempt).filter(
        QuizAttempt.assessment_id == assessment_id,
        QuizAttempt.student_id == context.user_id,
        QuizAttempt.status.in_(["needs_review", "graded"]),
    ).first()
    if completed:
        raise HTTPException(status_code=409, detail="this assessment has already been submitted")
    attempt = QuizAttempt(
        school_id=context.school_id,
        assessment_id=assessment_id,
        student_id=context.user_id,
        started_at=datetime.now(timezone.utc),
        status="in_progress",
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(
    attempt_id: UUID,
    payload: AttemptSubmission,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    if context.role != "student":
        raise HTTPException(status_code=403, detail="only a learner can submit a quiz attempt")
    attempt = db.query(QuizAttempt).filter(
        QuizAttempt.id == attempt_id,
        QuizAttempt.school_id == context.school_id,
        QuizAttempt.student_id == context.user_id,
        QuizAttempt.status == "in_progress",
    ).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="open quiz attempt not found")
    assessment = db.get(Assessment, attempt.assessment_id)
    if not assessment or not assessment.is_published or not _student_can_take(db, context, assessment):
        raise HTTPException(status_code=403, detail="assessment is no longer available to this learner")
    questions = db.query(QuestionBankItem).filter(
        QuestionBankItem.school_id == context.school_id,
        QuestionBankItem.assessment_id == attempt.assessment_id,
        QuestionBankItem.status == "active",
    ).all()
    if not questions:
        raise HTTPException(status_code=409, detail="assessment has no active quiz questions")
    if sum((Decimal(str(item.points or 0)) for item in questions), Decimal("0")) != Decimal(str(assessment.max_score)):
        raise HTTPException(status_code=409, detail="online assessment score configuration changed; contact the teacher")

    total = Decimal("0")
    earned = Decimal("0")
    needs_review = False
    for question in questions:
        points = Decimal(str(question.points or 0))
        total += points
        answer = payload.responses.get(str(question.id))
        awarded: Decimal | None = None
        correct_label = None
        if question.question_type in {"multiple_choice", "true_false", "short_answer"} and question.correct_answer is not None:
            correct = _normalise(answer) == _normalise(question.correct_answer)
            awarded = points if correct else Decimal("0")
            earned += awarded
            correct_label = "true" if correct else "false"
        else:
            needs_review = True
        db.add(QuizResponse(
            attempt_id=attempt.id,
            question_id=question.id,
            answer=answer,
            is_correct=correct_label,
            awarded_points=awarded,
        ))
        if awarded is not None:
            _record_mastery(
                db,
                school_id=context.school_id,
                student_id=context.user_id,
                question=question,
                awarded=awarded,
                evidence=f"quiz:{attempt.assessment_id}",
            )

    attempt.score = earned
    attempt.max_score = total
    attempt.submitted_at = datetime.now(timezone.utc)
    attempt.status = "needs_review" if needs_review else "graded"
    if not needs_review:
        _sync_assessment_result(db, attempt=attempt)
        notify_user(
            db,
            school_id=context.school_id,
            user_id=context.user_id,
            event="quiz.graded",
            title="Quiz graded",
            message=assessment.title,
            data={"assessment_id": str(assessment.id), "attempt_id": str(attempt.id)},
        )
    db.commit()
    db.refresh(attempt)
    return attempt


@router.put("/responses/{response_id}/mark")
def mark_response(
    response_id: UUID,
    payload: ManualMark,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*ASSESSMENT_STAFF)),
):
    response = db.query(QuizResponse).join(QuizAttempt, QuizAttempt.id == QuizResponse.attempt_id).filter(
        QuizResponse.id == response_id,
        QuizAttempt.school_id == context.school_id,
    ).first()
    if not response:
        raise HTTPException(status_code=404, detail="quiz response not found")
    if response.awarded_points is not None:
        raise HTTPException(status_code=409, detail="quiz response has already been marked")

    attempt = db.get(QuizAttempt, response.attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="quiz attempt not found")
    assessment = db.get(Assessment, attempt.assessment_id)
    if not assessment or assessment.school_id != context.school_id:
        raise HTTPException(status_code=404, detail="assessment not found")
    _assert_can_manage_assessment(db, context, assessment)

    question = db.get(QuestionBankItem, response.question_id)
    if not question or question.school_id != context.school_id:
        raise HTTPException(status_code=404, detail="quiz question not found")
    points = Decimal(str(question.points or 0))
    if payload.awarded_points > points:
        raise HTTPException(status_code=422, detail="awarded points exceed question points")

    response.awarded_points = payload.awarded_points
    response.is_correct = "true" if payload.awarded_points == points else "false"
    _record_mastery(
        db,
        school_id=context.school_id,
        student_id=attempt.student_id,
        question=question,
        awarded=payload.awarded_points,
        evidence=f"quiz:{attempt.assessment_id}:manual",
    )
    db.flush()

    pending = db.query(QuizResponse).filter(
        QuizResponse.attempt_id == attempt.id,
        QuizResponse.awarded_points.is_(None),
    ).count()
    if pending == 0:
        rows = db.query(QuizResponse).filter(QuizResponse.attempt_id == attempt.id).all()
        attempt.score = sum((Decimal(str(row.awarded_points or 0)) for row in rows), Decimal("0"))
        attempt.status = "graded"
        attempt.submitted_at = attempt.submitted_at or datetime.now(timezone.utc)
        _sync_assessment_result(db, attempt=attempt)
        notify_user(
            db,
            school_id=context.school_id,
            user_id=attempt.student_id,
            event="quiz.graded",
            title="Quiz graded",
            message=assessment.title,
            data={"assessment_id": str(assessment.id), "attempt_id": str(attempt.id)},
        )

    db.commit()
    db.refresh(response)
    return response
