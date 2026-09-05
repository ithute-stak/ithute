from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import StudentEnrollment, Teacher
from database.multi_tenant_school_management.models.tutor_completion import (
    Assignment,
    AssignmentSubmission,
    Lesson,
    MasteryRecord,
    QuestionBankItem,
    StudyPlan,
)
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles
from utils.tutor_notifications import notify_user

router = APIRouter(prefix="/lms", tags=["Learning & Tutor"])
WRITERS = ("school_admin", "principal", "vice_principal", "teacher", "class_teacher")
TEACHER_ROLES = {"teacher", "class_teacher"}


class LessonCreate(BaseModel):
    class_id: UUID
    subject_id: UUID
    title: str = Field(min_length=2, max_length=200)
    summary: str | None = None
    body: str | None = None
    resource_url: str | None = None
    sequence: int = Field(default=1, ge=1)


class AssignmentCreate(BaseModel):
    class_id: UUID
    subject_id: UUID
    title: str = Field(min_length=2, max_length=200)
    instructions: str = Field(min_length=2)
    due_at: datetime | None = None
    max_score: Decimal = Field(default=Decimal("100"), gt=0)
    allow_resubmission: bool = True


class SubmissionCreate(BaseModel):
    answer_text: str | None = None
    attachment_url: str | None = None


class GradeSubmission(BaseModel):
    score: Decimal = Field(ge=0)
    feedback: str | None = None


class QuestionCreate(BaseModel):
    subject_id: UUID
    class_id: UUID | None = None
    assessment_id: UUID | None = None
    topic_key: str | None = None
    prompt: str = Field(min_length=2)
    question_type: Literal["multiple_choice", "true_false", "short_answer", "long_answer"] = "short_answer"
    choices: list[str] | None = None
    correct_answer: object | None = None
    points: Decimal = Field(default=Decimal("1"), gt=0)
    explanation: str | None = None


class MasteryUpdate(BaseModel):
    subject_id: UUID
    topic_key: str = Field(min_length=1, max_length=160)
    mastery_score: Decimal = Field(ge=0, le=100)
    evidence: str | None = None


class StudyPlanCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    reason: str | None = None
    items: list[dict] = Field(default_factory=list)


def _teacher_profile_id(db: Session, context: SchoolContext) -> UUID | None:
    if context.role not in TEACHER_ROLES:
        return None
    teacher = db.query(Teacher).filter(
        Teacher.user_id == context.user_id,
        Teacher.school_id == context.school_id,
    ).first()
    if not teacher:
        raise HTTPException(status_code=403, detail="teacher profile is not linked to this school workspace")
    return teacher.id


def _require_assignment_owner(db: Session, context: SchoolContext, assignment: Assignment) -> None:
    if context.role in TEACHER_ROLES:
        teacher_id = _teacher_profile_id(db, context)
        if assignment.teacher_id != teacher_id:
            raise HTTPException(status_code=403, detail="assignment belongs to another teacher")


def _require_lesson_owner(db: Session, context: SchoolContext, lesson: Lesson) -> None:
    if context.role in TEACHER_ROLES:
        teacher_id = _teacher_profile_id(db, context)
        if lesson.teacher_id != teacher_id:
            raise HTTPException(status_code=403, detail="lesson belongs to another teacher")


@router.get("/lessons")
def list_lessons(
    class_id: UUID | None = None,
    subject_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(Lesson).filter(Lesson.school_id == context.school_id)
    if context.role == "student":
        enrollment = db.query(StudentEnrollment).filter(
            StudentEnrollment.school_id == context.school_id,
            StudentEnrollment.student_id == context.user_id,
            StudentEnrollment.is_current.is_(True),
        ).first()
        if not enrollment or enrollment.class_id is None:
            return []
        query = query.filter(Lesson.class_id == enrollment.class_id, Lesson.status == "published")
    elif class_id:
        query = query.filter(Lesson.class_id == class_id)
    if subject_id:
        query = query.filter(Lesson.subject_id == subject_id)
    return query.order_by(Lesson.sequence.asc(), Lesson.created_at.desc()).all()


@router.post("/lessons")
def create_lesson(
    payload: LessonCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    lesson = Lesson(
        school_id=context.school_id,
        teacher_id=_teacher_profile_id(db, context),
        **payload.model_dump(),
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.put("/lessons/{lesson_id}/publish")
def publish_lesson(
    lesson_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    lesson = db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.school_id == context.school_id).first()
    if not lesson:
        raise HTTPException(status_code=404, detail="lesson not found")
    _require_lesson_owner(db, context, lesson)
    lesson.status = "published"
    lesson.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lesson)
    return lesson


@router.get("/assignments")
def list_assignments(
    class_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(Assignment).filter(Assignment.school_id == context.school_id)
    if context.role == "student":
        enrollment = db.query(StudentEnrollment).filter(
            StudentEnrollment.school_id == context.school_id,
            StudentEnrollment.student_id == context.user_id,
            StudentEnrollment.is_current.is_(True),
        ).first()
        if not enrollment:
            return []
        query = query.filter(Assignment.class_id == enrollment.class_id, Assignment.status == "published")
    elif context.role in TEACHER_ROLES:
        query = query.filter(Assignment.teacher_id == _teacher_profile_id(db, context))
        if class_id:
            query = query.filter(Assignment.class_id == class_id)
    elif class_id:
        query = query.filter(Assignment.class_id == class_id)
    return query.order_by(Assignment.due_at.asc().nullslast(), Assignment.created_at.desc()).all()


@router.post("/assignments")
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    assignment = Assignment(
        school_id=context.school_id,
        teacher_id=_teacher_profile_id(db, context),
        **payload.model_dump(),
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.put("/assignments/{assignment_id}/publish")
def publish_assignment(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id, Assignment.school_id == context.school_id).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="assignment not found")
    _require_assignment_owner(db, context, assignment)
    assignment.status = "published"
    assignment.published_at = datetime.now(timezone.utc)
    student_ids = [row.student_id for row in db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.class_id == assignment.class_id,
        StudentEnrollment.is_current.is_(True),
    ).all()]
    for student_id in student_ids:
        notify_user(
            db,
            school_id=context.school_id,
            user_id=student_id,
            event="assignment.published",
            title="New assignment",
            message=assignment.title,
            data={"id": str(assignment.id)},
        )
    db.commit()
    db.refresh(assignment)
    return assignment


@router.post("/assignments/{assignment_id}/submissions")
def submit_assignment(
    assignment_id: UUID,
    payload: SubmissionCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    if context.role != "student" and not context.is_platform_admin:
        raise HTTPException(status_code=403, detail="only a learner can submit an assignment")
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.school_id == context.school_id,
        Assignment.status == "published",
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="published assignment not found")
    enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.student_id == context.user_id,
        StudentEnrollment.class_id == assignment.class_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    if not enrollment:
        raise HTTPException(status_code=403, detail="assignment does not belong to your active class")
    previous = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.student_id == context.user_id,
    ).order_by(AssignmentSubmission.attempt_no.desc()).first()
    if previous and not assignment.allow_resubmission:
        raise HTTPException(status_code=409, detail="resubmission is disabled")
    submission = AssignmentSubmission(
        school_id=context.school_id,
        assignment_id=assignment_id,
        student_id=context.user_id,
        attempt_no=(previous.attempt_no + 1 if previous else 1),
        answer_text=payload.answer_text,
        attachment_url=payload.attachment_url,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/assignments/{assignment_id}/submissions")
def list_submissions(
    assignment_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.school_id == context.school_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="assignment not found")
    _require_assignment_owner(db, context, assignment)
    return db.query(AssignmentSubmission).filter(
        AssignmentSubmission.school_id == context.school_id,
        AssignmentSubmission.assignment_id == assignment_id,
    ).order_by(AssignmentSubmission.submitted_at.desc()).all()


@router.put("/submissions/{submission_id}/grade")
def grade_submission(
    submission_id: UUID,
    payload: GradeSubmission,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    submission = db.query(AssignmentSubmission).filter(
        AssignmentSubmission.id == submission_id,
        AssignmentSubmission.school_id == context.school_id,
    ).first()
    if not submission:
        raise HTTPException(status_code=404, detail="submission not found")
    assignment = db.query(Assignment).filter(
        Assignment.id == submission.assignment_id,
        Assignment.school_id == context.school_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="assignment not found")
    _require_assignment_owner(db, context, assignment)
    if payload.score > assignment.max_score:
        raise HTTPException(status_code=422, detail="score cannot exceed assignment maximum")
    submission.score = payload.score
    submission.feedback = payload.feedback
    submission.status = "graded"
    submission.graded_by = context.user_id
    submission.graded_at = datetime.now(timezone.utc)
    notify_user(
        db,
        school_id=context.school_id,
        user_id=submission.student_id,
        event="assignment.graded",
        title="Assignment marked",
        message=assignment.title,
        data={"id": str(submission.id)},
    )
    db.commit()
    db.refresh(submission)
    return submission


@router.post("/question-bank")
def create_question(
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    question = QuestionBankItem(school_id=context.school_id, **payload.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.get("/question-bank")
def list_questions(
    subject_id: UUID | None = None,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    query = db.query(QuestionBankItem).filter(QuestionBankItem.school_id == context.school_id)
    if subject_id:
        query = query.filter(QuestionBankItem.subject_id == subject_id)
    return query.order_by(QuestionBankItem.created_at.desc()).all()


@router.put("/students/{student_id}/mastery")
def update_mastery(
    student_id: UUID,
    payload: MasteryUpdate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    record = db.query(MasteryRecord).filter(
        MasteryRecord.school_id == context.school_id,
        MasteryRecord.student_id == student_id,
        MasteryRecord.subject_id == payload.subject_id,
        MasteryRecord.topic_key == payload.topic_key,
    ).first()
    if not record:
        record = MasteryRecord(
            school_id=context.school_id,
            student_id=student_id,
            subject_id=payload.subject_id,
            topic_key=payload.topic_key,
        )
        db.add(record)
    record.mastery_score = payload.mastery_score
    record.evidence_count = (record.evidence_count or 0) + 1
    record.last_evidence = payload.evidence
    record.last_evidence_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(record)
    return record


@router.get("/students/{student_id}/mastery")
def learner_mastery(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    if context.role == "student" and context.user_id != student_id:
        raise HTTPException(status_code=403, detail="cannot view another learner's mastery profile")
    return db.query(MasteryRecord).filter(
        MasteryRecord.school_id == context.school_id,
        MasteryRecord.student_id == student_id,
    ).order_by(MasteryRecord.mastery_score.asc()).all()


@router.post("/students/{student_id}/study-plans")
def create_study_plan(
    student_id: UUID,
    payload: StudyPlanCreate,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*WRITERS)),
):
    plan = StudyPlan(school_id=context.school_id, student_id=student_id, **payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/students/{student_id}/study-plans")
def list_study_plans(
    student_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    if context.role == "student" and context.user_id != student_id:
        raise HTTPException(status_code=403, detail="cannot view another learner's study plan")
    return db.query(StudyPlan).filter(
        StudyPlan.school_id == context.school_id,
        StudyPlan.student_id == student_id,
        StudyPlan.status == "active",
    ).order_by(StudyPlan.created_at.desc()).all()
