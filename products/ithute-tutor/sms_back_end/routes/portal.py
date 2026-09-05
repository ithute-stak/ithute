from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import ParentStudent, StudentEnrollment, Teacher
from database.multi_tenant_school_management.models.academic_core import AssessmentResult, TeachingAssignment
from database.multi_tenant_school_management.models.tutor_completion import Assignment, AssignmentSubmission, MasteryRecord, StudyPlan
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context

router = APIRouter(prefix="/portal", tags=["Role Portals"])


def _student_snapshot(db: Session, context: SchoolContext, student_id):
    enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    assignments = []
    if enrollment and enrollment.class_id:
        assignments = db.query(Assignment).filter(
            Assignment.school_id == context.school_id,
            Assignment.class_id == enrollment.class_id,
            Assignment.status == "published",
        ).order_by(Assignment.due_at.asc().nullslast()).limit(20).all()
    return {
        "student_id": student_id,
        "enrollment": enrollment,
        "assignments": assignments,
        "submissions": db.query(AssignmentSubmission).filter(
            AssignmentSubmission.school_id == context.school_id,
            AssignmentSubmission.student_id == student_id,
        ).order_by(AssignmentSubmission.created_at.desc()).limit(20).all(),
        "results": db.query(AssessmentResult).filter(
            AssessmentResult.school_id == context.school_id,
            AssessmentResult.student_id == student_id,
        ).order_by(AssessmentResult.created_at.desc()).limit(20).all(),
        "mastery": db.query(MasteryRecord).filter(
            MasteryRecord.school_id == context.school_id,
            MasteryRecord.student_id == student_id,
        ).order_by(MasteryRecord.mastery_score.asc()).limit(30).all(),
        "study_plans": db.query(StudyPlan).filter(
            StudyPlan.school_id == context.school_id,
            StudyPlan.student_id == student_id,
            StudyPlan.status == "active",
        ).order_by(StudyPlan.created_at.desc()).all(),
    }


@router.get("/me")
def my_portal(db: Session = Depends(get_db), context: SchoolContext = Depends(get_school_context)):
    if context.role == "student":
        return {"portal": "student", **_student_snapshot(db, context, context.user_id)}

    if context.role == "parent":
        links = db.query(ParentStudent).filter(ParentStudent.parent_id == context.user_id).all()
        return {
            "portal": "parent",
            "children": [_student_snapshot(db, context, link.student_id) for link in links],
        }

    if context.role in {"teacher", "class_teacher"}:
        teacher = db.query(Teacher).filter(
            Teacher.user_id == context.user_id,
            Teacher.school_id == context.school_id,
        ).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="teacher profile is not linked to this school workspace")
        assignments = db.query(TeachingAssignment).filter(
            TeachingAssignment.school_id == context.school_id,
            TeachingAssignment.teacher_id == teacher.id,
            TeachingAssignment.is_active.is_(True),
        ).all()
        return {
            "portal": "teacher",
            "teaching_assignments": assignments,
            "pending_marking": db.query(AssignmentSubmission).join(
                Assignment, Assignment.id == AssignmentSubmission.assignment_id
            ).filter(
                AssignmentSubmission.school_id == context.school_id,
                Assignment.teacher_id == teacher.id,
                AssignmentSubmission.status == "submitted",
            ).order_by(AssignmentSubmission.submitted_at.asc()).limit(50).all(),
        }

    return {
        "portal": "management",
        "role": context.role,
        "school_id": context.school_id,
        "active_students": db.query(StudentEnrollment).filter(
            StudentEnrollment.school_id == context.school_id,
            StudentEnrollment.is_current.is_(True),
        ).count(),
        "pending_submissions": db.query(AssignmentSubmission).filter(
            AssignmentSubmission.school_id == context.school_id,
            AssignmentSubmission.status == "submitted",
        ).count(),
    }
