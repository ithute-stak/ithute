import hashlib
import secrets
from collections import Counter
from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import (
    Class,
    Grade,
    Person,
    School,
    SchoolClass,
    SchoolMembership,
    Student,
    StudentAttendance,
    StudentEnrollment,
    Subject,
)
from database.multi_tenant_school_management.models.academic_core import (
    AcademicTerm,
    AcademicYear,
    Assessment,
    AssessmentResult,
)
from database.multi_tenant_school_management.models.student_transfer import StudentTransfer, StudentTransferEvent
from database.session import get_db
from utils.school_context import SchoolContext, get_school_context, require_school_roles

router = APIRouter(prefix="/student-transfers", tags=["Student Transfers"])
TRANSFER_MANAGERS = ("school_admin", "principal", "vice_principal", "registrar", "admissions_officer")

ACTIVE_TRANSFER_STATUSES = {"released", "under_review"}


class TransferIssue(BaseModel):
    transfer_reason: str = Field(min_length=2, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    consent_confirmed: bool = False
    validity_days: int = Field(default=7, ge=1, le=30)


class TransferClaim(BaseModel):
    code: str = Field(min_length=12, max_length=200)


class TransferAccept(BaseModel):
    class_id: UUID
    start_date: date = Field(default_factory=date.today)
    records_verified: bool = False
    destination_note: str | None = Field(default=None, max_length=1000)


class TransferReject(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class TransferCancel(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.utcnow()


def _reference(db: Session) -> str:
    year = _now().year
    for _ in range(20):
        value = f"TR-{year}-{secrets.token_hex(5).upper()}"
        if not db.query(StudentTransfer.id).filter(StudentTransfer.reference_number == value).first():
            return value
    raise HTTPException(503, "Unable to allocate a unique transfer reference")


def _period(db: Session, school_id: UUID, when: date):
    year = db.query(AcademicYear).filter(
        AcademicYear.school_id == school_id,
        AcademicYear.start_date <= when,
        AcademicYear.end_date >= when,
    ).first()
    term = db.query(AcademicTerm).filter(
        AcademicTerm.school_id == school_id,
        AcademicTerm.start_date <= when,
        AcademicTerm.end_date >= when,
    ).first()
    return year, term


def _event(
    db: Session,
    transfer: StudentTransfer,
    context: SchoolContext | None,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    note: str | None = None,
    metadata: dict | None = None,
    school_id: UUID | None = None,
):
    db.add(StudentTransferEvent(
        transfer_id=transfer.id,
        school_id=school_id or (context.school_id if context else transfer.source_school_id),
        actor_user_id=context.user_id if context else None,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        note=note,
        metadata_json=metadata or {},
    ))


def _load_transfer(db: Session, transfer_id: UUID) -> StudentTransfer:
    transfer = db.get(StudentTransfer, transfer_id)
    if transfer is None:
        raise HTTPException(404, "Transfer not found")
    return transfer


def _require_party(transfer: StudentTransfer, context: SchoolContext):
    if context.is_platform_admin:
        return
    if context.school_id not in {transfer.source_school_id, transfer.destination_school_id}:
        raise HTTPException(403, "This school is not a party to this learner transfer")


def _require_source(transfer: StudentTransfer, context: SchoolContext):
    if not context.is_platform_admin and transfer.source_school_id != context.school_id:
        raise HTTPException(403, "Only the releasing school can perform this action")


def _require_destination(transfer: StudentTransfer, context: SchoolContext):
    if transfer.destination_school_id != context.school_id:
        raise HTTPException(403, "Only the receiving school can perform this action")


def _expire_if_needed(db: Session, transfer: StudentTransfer) -> bool:
    if transfer.status == "released" and transfer.expires_at < _now():
        previous = transfer.status
        transfer.status = "expired"
        _event(db, transfer, None, "expired", previous, transfer.status, "Transfer claim window expired")
        return True
    return False


def _school_names(db: Session, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    return {row.id: row.name for row in db.query(School).filter(School.id.in_(ids)).all()}


def _serialize_transfer(db: Session, item: StudentTransfer, context: SchoolContext) -> dict:
    schools = _school_names(db, {item.source_school_id} | ({item.destination_school_id} if item.destination_school_id else set()))
    events = db.query(StudentTransferEvent).filter(
        StudentTransferEvent.transfer_id == item.id
    ).order_by(StudentTransferEvent.created_at.asc()).all()
    direction = "outgoing" if item.source_school_id == context.school_id else "incoming"
    if context.is_platform_admin and item.source_school_id != context.school_id and item.destination_school_id != context.school_id:
        direction = "platform"
    return {
        "id": str(item.id),
        "reference_number": item.reference_number,
        "student_id": str(item.student_id),
        "source_school_id": str(item.source_school_id),
        "source_school": schools.get(item.source_school_id),
        "destination_school_id": str(item.destination_school_id) if item.destination_school_id else None,
        "destination_school": schools.get(item.destination_school_id) if item.destination_school_id else None,
        "direction": direction,
        "status": item.status,
        "transfer_reason": item.transfer_reason,
        "note": item.note,
        "destination_note": item.destination_note,
        "rejection_reason": item.rejection_reason,
        "consent_confirmed": item.consent_confirmed,
        "records_verified": item.records_verified,
        "expires_at": item.expires_at.isoformat(),
        "released_at": item.released_at.isoformat() if item.released_at else None,
        "claimed_at": item.claimed_at.isoformat() if item.claimed_at else None,
        "accepted_at": item.accepted_at.isoformat() if item.accepted_at else None,
        "rejected_at": item.rejected_at.isoformat() if item.rejected_at else None,
        "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
        "proposed_start_date": item.proposed_start_date.isoformat() if item.proposed_start_date else None,
        "destination_class_id": str(item.destination_class_id) if item.destination_class_id else None,
        "review_available": item.status == "under_review" and item.destination_school_id == context.school_id,
        "records_available": item.status == "accepted",
        "events": [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "from_status": row.from_status,
                "to_status": row.to_status,
                "school_id": str(row.school_id) if row.school_id else None,
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "note": row.note,
                "metadata": row.metadata_json or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in events
        ],
    }


def _record_school_ids(db: Session, transfer: StudentTransfer, context: SchoolContext) -> set[UUID]:
    if transfer.status != "accepted" or transfer.destination_school_id is None:
        raise HTTPException(409, "Full learner history becomes shareable only after the transfer is accepted")

    _require_party(transfer, context)

    if not context.is_platform_admin and context.school_id == transfer.source_school_id:
        return {transfer.source_school_id}

    if transfer.accepted_at is None:
        raise HTTPException(409, "Accepted transfer is missing its acceptance timestamp")

    lineage = db.query(StudentTransfer).filter(
        StudentTransfer.student_id == transfer.student_id,
        StudentTransfer.status == "accepted",
        StudentTransfer.accepted_at.is_not(None),
        StudentTransfer.accepted_at <= transfer.accepted_at,
    ).order_by(StudentTransfer.accepted_at.asc()).all()
    school_ids = {row.source_school_id for row in lineage}
    school_ids.add(transfer.source_school_id)
    return school_ids


@router.post("/{student_id}/issue", status_code=201)
def issue_transfer_code(
    student_id: UUID,
    payload: TransferIssue,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*TRANSFER_MANAGERS)),
):
    if not payload.consent_confirmed:
        raise HTTPException(400, "Confirm learner/guardian transfer authorization before releasing the learner")

    enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    if enrollment is None:
        raise HTTPException(404, "Active learner enrolment not found in this school")

    reviewing = db.query(StudentTransfer).filter(
        StudentTransfer.student_id == student_id,
        StudentTransfer.source_school_id == context.school_id,
        StudentTransfer.status == "under_review",
    ).first()
    if reviewing:
        raise HTTPException(409, f"Transfer {reviewing.reference_number or reviewing.id} is already under review by another school")

    old_releases = db.query(StudentTransfer).filter(
        StudentTransfer.student_id == student_id,
        StudentTransfer.source_school_id == context.school_id,
        StudentTransfer.status == "released",
    ).all()
    for old in old_releases:
        previous = old.status
        old.status = "cancelled"
        old.cancelled_at = _now()
        old.cancelled_by = context.user_id
        _event(db, old, context, "superseded", previous, old.status, "Superseded by a new transfer release")

    raw_code = secrets.token_urlsafe(18)
    transfer = StudentTransfer(
        student_id=student_id,
        source_school_id=context.school_id,
        reference_number=_reference(db),
        code_hash=_hash(raw_code),
        status="released",
        transfer_reason=payload.transfer_reason.strip(),
        note=payload.note.strip() if payload.note else None,
        consent_confirmed=True,
        expires_at=_now() + timedelta(days=payload.validity_days),
        released_at=_now(),
        released_by=context.user_id,
    )
    db.add(transfer)
    db.flush()
    _event(db, transfer, context, "released", None, "released", payload.note, {
        "transfer_reason": payload.transfer_reason,
        "validity_days": payload.validity_days,
        "consent_confirmed": True,
    })
    db.commit()
    db.refresh(transfer)
    return {
        "transfer_id": str(transfer.id),
        "reference_number": transfer.reference_number,
        "student_id": str(student_id),
        "code": raw_code,
        "status": transfer.status,
        "expires_at": transfer.expires_at.isoformat(),
        "message": "Transfer released. Share the one-time claim code with the receiving school; claiming does not complete admission.",
    }


@router.post("/claim")
def claim_transfer(
    payload: TransferClaim,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*TRANSFER_MANAGERS)),
):
    transfer = db.query(StudentTransfer).filter(
        StudentTransfer.code_hash == _hash(payload.code),
        StudentTransfer.status == "released",
    ).with_for_update().first()
    if transfer is None:
        raise HTTPException(404, "Transfer code is invalid, already claimed, or no longer active")
    if _expire_if_needed(db, transfer):
        db.commit()
        raise HTTPException(410, "Transfer code has expired")
    if transfer.source_school_id == context.school_id:
        raise HTTPException(400, "The releasing school cannot claim its own transfer")

    active_here = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == transfer.student_id,
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    if active_here:
        raise HTTPException(409, "Learner already has an active enrolment in this school")

    previous = transfer.status
    transfer.destination_school_id = context.school_id
    transfer.status = "under_review"
    transfer.claimed_at = _now()
    transfer.claimed_by = context.user_id
    _event(db, transfer, context, "claimed", previous, transfer.status, "Receiving school claimed transfer for admission review")
    db.commit()
    return {
        "message": "Transfer claimed for review; no enrolment has been moved yet",
        "transfer_id": str(transfer.id),
        "reference_number": transfer.reference_number,
        "status": transfer.status,
        "review_url": f"/student-transfers/{transfer.id}/review",
    }


@router.post("/redeem")
def legacy_redeem_transfer_code():
    raise HTTPException(
        409,
        "Transfer workflow upgraded: claim the code first, review the learner packet, then explicitly accept or reject the transfer",
    )


@router.get("/{transfer_id}/review")
def review_transfer_packet(
    transfer_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    transfer = _load_transfer(db, transfer_id)
    _require_party(transfer, context)
    if transfer.status != "under_review":
        raise HTTPException(410, "Admission-review packet access closes when the transfer leaves under-review status")

    student = db.get(Student, transfer.student_id)
    person = db.get(Person, transfer.student_id)
    source_school = db.get(School, transfer.source_school_id)
    if student is None:
        raise HTTPException(404, "Learner identity no longer exists")

    current_enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == transfer.student_id,
        StudentEnrollment.school_id == transfer.source_school_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    classroom = db.get(Class, current_enrollment.class_id) if current_enrollment and current_enrollment.class_id else None
    grade = db.get(Grade, classroom.grade_id) if classroom and classroom.grade_id else None

    attendance_rows = db.query(StudentAttendance).filter(
        StudentAttendance.student_id == transfer.student_id,
        StudentAttendance.school_id == transfer.source_school_id,
    ).order_by(StudentAttendance.attendance_date.desc()).limit(180).all()
    attendance_counts = Counter(row.status for row in attendance_rows)

    result_rows = (
        db.query(AssessmentResult, Assessment)
        .join(Assessment, Assessment.id == AssessmentResult.assessment_id)
        .filter(
            AssessmentResult.student_id == transfer.student_id,
            Assessment.school_id == transfer.source_school_id,
            Assessment.is_published.is_(True),
        )
        .order_by(Assessment.assessment_date.desc(), Assessment.title.asc())
        .limit(20)
        .all()
    )
    subject_ids = {assessment.subject_id for _, assessment in result_rows if assessment.subject_id}
    subjects = {
        row.id: row.name for row in db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
    } if subject_ids else {}

    recent_results = []
    for result, assessment in result_rows:
        percentage = None
        if result.score is not None and assessment.max_score:
            percentage = round(float(result.score / assessment.max_score * 100), 2)
        recent_results.append({
            "assessment_date": assessment.assessment_date.isoformat(),
            "title": assessment.title,
            "assessment_type": assessment.assessment_type,
            "subject": subjects.get(assessment.subject_id),
            "score": float(result.score) if result.score is not None else None,
            "max_score": float(assessment.max_score),
            "percentage": percentage,
            "is_absent": result.is_absent,
            "remarks": result.remarks,
        })

    return {
        "transfer": _serialize_transfer(db, transfer, context),
        "learner": {
            "id": str(student.id),
            "admission_number": student.admission_number,
            "first_name": person.first_name if person else None,
            "last_name": person.last_name if person else None,
            "date_of_birth": person.date_of_birth.isoformat() if person and person.date_of_birth else None,
            "gender": getattr(person.gender, "value", person.gender) if person else None,
            "nationality": person.nationality if person else None,
        },
        "source_school": {
            "id": str(transfer.source_school_id),
            "name": source_school.name if source_school else None,
        },
        "current_enrollment": {
            "id": str(current_enrollment.id) if current_enrollment else None,
            "class_id": str(classroom.id) if classroom else None,
            "class": classroom.name if classroom else None,
            "grade": grade.name if grade else None,
            "academic_year": current_enrollment.academic_year if current_enrollment else None,
            "term": current_enrollment.term if current_enrollment else None,
            "start_date": current_enrollment.start_date.isoformat() if current_enrollment and current_enrollment.start_date else None,
        },
        "attendance_summary": {
            "records_reviewed": len(attendance_rows),
            "present": attendance_counts.get("present", 0),
            "absent": attendance_counts.get("absent", 0),
            "late": attendance_counts.get("late", 0),
            "excused": attendance_counts.get("excused", 0),
        },
        "published_academic_summary": recent_results,
        "privacy": {
            "scope": "admission-review transfer packet",
            "full_history_available_after_acceptance": True,
            "finance_shared": False,
            "source_records_mutable_by_destination": False,
        },
    }


@router.post("/{transfer_id}/accept")
def accept_transfer(
    transfer_id: UUID,
    payload: TransferAccept,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*TRANSFER_MANAGERS)),
):
    transfer = db.query(StudentTransfer).filter(StudentTransfer.id == transfer_id).with_for_update().first()
    if transfer is None:
        raise HTTPException(404, "Transfer not found")
    _require_destination(transfer, context)
    if transfer.status != "under_review":
        raise HTTPException(409, "Only a transfer under admission review can be accepted")
    if payload.start_date > date.today():
        raise HTTPException(400, "Final acceptance cannot occur before the effective transfer date; keep the case under review until that date")
    if not payload.records_verified:
        raise HTTPException(400, "Confirm that the receiving school reviewed the transfer packet before acceptance")

    class_link = db.query(SchoolClass).filter(
        SchoolClass.school_id == context.school_id,
        SchoolClass.class_id == payload.class_id,
    ).first()
    if class_link is None:
        raise HTTPException(404, "Selected class is not enabled in the receiving school")

    source_enrollment = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == transfer.student_id,
        StudentEnrollment.school_id == transfer.source_school_id,
        StudentEnrollment.is_current.is_(True),
    ).with_for_update().first()
    if source_enrollment is None:
        raise HTTPException(409, "The source enrolment is no longer active; transfer cannot be completed")

    destination_existing = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == transfer.student_id,
        StudentEnrollment.school_id == context.school_id,
        StudentEnrollment.is_current.is_(True),
    ).first()
    if destination_existing:
        raise HTTPException(409, "Learner already has an active enrolment in this school")

    student = db.get(Student, transfer.student_id)
    if student is None:
        raise HTTPException(404, "Learner identity no longer exists")

    previous = transfer.status
    source_end = payload.start_date
    if source_enrollment.start_date and payload.start_date > source_enrollment.start_date:
        source_end = payload.start_date - timedelta(days=1)
    source_enrollment.end_date = source_end
    source_enrollment.status = "transferred"
    source_enrollment.transfer_destination = "Transferred through !thute Tutor"
    source_enrollment.is_current = False

    source_membership = db.query(SchoolMembership).filter(
        SchoolMembership.user_id == transfer.student_id,
        SchoolMembership.school_id == transfer.source_school_id,
    ).first()
    if source_membership:
        source_membership.is_active = False

    year, term = _period(db, context.school_id, payload.start_date)
    destination = StudentEnrollment(
        student_id=transfer.student_id,
        school_id=context.school_id,
        class_id=payload.class_id,
        start_date=payload.start_date,
        academic_year_id=year.id if year else None,
        term_id=term.id if term else None,
        academic_year=year.name if year else None,
        term=term.name if term else None,
        status="active",
        is_current=True,
    )
    db.add(destination)

    membership = db.query(SchoolMembership).filter(
        SchoolMembership.user_id == transfer.student_id,
        SchoolMembership.school_id == context.school_id,
    ).first()
    if membership is None:
        db.add(SchoolMembership(
            user_id=transfer.student_id,
            school_id=context.school_id,
            role="student",
            title="Student",
            is_active=True,
            is_default=False,
        ))
    else:
        membership.is_active = True
        membership.role = "student"

    student.class_id = payload.class_id
    transfer.status = "accepted"
    transfer.proposed_start_date = payload.start_date
    transfer.destination_class_id = payload.class_id
    transfer.records_verified = True
    transfer.destination_note = payload.destination_note.strip() if payload.destination_note else None
    transfer.accepted_at = _now()
    transfer.accepted_by = context.user_id
    _event(db, transfer, context, "accepted", previous, transfer.status, transfer.destination_note, {
        "start_date": payload.start_date.isoformat(),
        "class_id": str(payload.class_id),
        "records_verified": True,
    })
    db.commit()
    db.refresh(destination)
    return {
        "message": "Learner transfer formally accepted and enrolment activated",
        "reference_number": transfer.reference_number,
        "student_id": str(transfer.student_id),
        "source_school_id": str(transfer.source_school_id),
        "destination_school_id": str(context.school_id),
        "enrollment_id": str(destination.id),
        "records_url": f"/student-transfers/{transfer.id}/records",
    }


@router.post("/{transfer_id}/reject")
def reject_transfer(
    transfer_id: UUID,
    payload: TransferReject,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*TRANSFER_MANAGERS)),
):
    transfer = db.query(StudentTransfer).filter(StudentTransfer.id == transfer_id).with_for_update().first()
    if transfer is None:
        raise HTTPException(404, "Transfer not found")
    _require_destination(transfer, context)
    if transfer.status != "under_review":
        raise HTTPException(409, "Only a transfer under admission review can be rejected")
    previous = transfer.status
    transfer.status = "rejected"
    transfer.rejection_reason = payload.reason.strip()
    transfer.rejected_at = _now()
    transfer.rejected_by = context.user_id
    _event(db, transfer, context, "rejected", previous, transfer.status, transfer.rejection_reason)
    db.commit()
    return {
        "message": "Transfer application rejected; learner remains active at the releasing school",
        "reference_number": transfer.reference_number,
        "status": transfer.status,
    }


@router.post("/{transfer_id}/cancel")
def cancel_transfer(
    transfer_id: UUID,
    payload: TransferCancel,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(require_school_roles(*TRANSFER_MANAGERS)),
):
    transfer = db.query(StudentTransfer).filter(StudentTransfer.id == transfer_id).with_for_update().first()
    if transfer is None:
        raise HTTPException(404, "Transfer not found")
    _require_source(transfer, context)
    if transfer.status not in ACTIVE_TRANSFER_STATUSES:
        raise HTTPException(409, "Only a released or under-review transfer can be cancelled")
    previous = transfer.status
    transfer.status = "cancelled"
    transfer.cancelled_at = _now()
    transfer.cancelled_by = context.user_id
    _event(db, transfer, context, "cancelled", previous, transfer.status, payload.reason.strip())
    db.commit()
    return {
        "message": "Transfer cancelled; learner remains active at the releasing school",
        "reference_number": transfer.reference_number,
        "status": transfer.status,
    }


@router.get("")
def list_school_transfers(
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    query = db.query(StudentTransfer)
    if not context.is_platform_admin:
        query = query.filter(
            (StudentTransfer.source_school_id == context.school_id) |
            (StudentTransfer.destination_school_id == context.school_id)
        )
    rows = query.order_by(StudentTransfer.created_at.desc()).limit(300).all()
    changed = False
    for row in rows:
        changed = _expire_if_needed(db, row) or changed
    if changed:
        db.commit()
    return [_serialize_transfer(db, item, context) for item in rows]


@router.get("/{transfer_id}/records")
def transferred_learner_records(
    transfer_id: UUID,
    db: Session = Depends(get_db),
    context: SchoolContext = Depends(get_school_context),
):
    transfer = _load_transfer(db, transfer_id)
    school_ids = _record_school_ids(db, transfer, context)

    student = db.get(Student, transfer.student_id)
    person = db.get(Person, transfer.student_id)
    if student is None:
        raise HTTPException(404, "Learner identity not found")

    schools = _school_names(db, school_ids)
    years = {
        row.id: row
        for row in db.query(AcademicYear).filter(AcademicYear.school_id.in_(school_ids)).all()
    }
    terms = {
        row.id: row
        for row in db.query(AcademicTerm).filter(AcademicTerm.school_id.in_(school_ids)).all()
    }

    enrollments = db.query(StudentEnrollment).filter(
        StudentEnrollment.student_id == transfer.student_id,
        StudentEnrollment.school_id.in_(school_ids),
    ).order_by(StudentEnrollment.start_date.asc()).all()
    attendance = db.query(StudentAttendance).filter(
        StudentAttendance.student_id == transfer.student_id,
        StudentAttendance.school_id.in_(school_ids),
    ).order_by(StudentAttendance.attendance_date.asc()).all()

    class_ids = {
        row.class_id for row in enrollments if row.class_id
    } | {
        row.classroom_id for row in attendance if row.classroom_id
    }

    result_rows = (
        db.query(AssessmentResult, Assessment)
        .join(Assessment, Assessment.id == AssessmentResult.assessment_id)
        .filter(
            AssessmentResult.student_id == transfer.student_id,
            Assessment.school_id.in_(school_ids),
            Assessment.is_published.is_(True),
        )
        .order_by(Assessment.assessment_date.asc(), Assessment.title.asc())
        .all()
    )
    class_ids |= {assessment.class_id for _, assessment in result_rows if assessment.class_id}
    subject_ids = {assessment.subject_id for _, assessment in result_rows if assessment.subject_id}

    classes = {
        row.id: row
        for row in db.query(Class).filter(Class.id.in_(class_ids)).all()
    } if class_ids else {}
    grade_ids = {row.grade_id for row in classes.values() if row.grade_id}
    grades = {
        row.id: row.name
        for row in db.query(Grade).filter(Grade.id.in_(grade_ids)).all()
    } if grade_ids else {}
    subjects = {
        row.id: row.name
        for row in db.query(Subject).filter(Subject.id.in_(subject_ids)).all()
    } if subject_ids else {}

    def class_payload(class_id: UUID | None):
        classroom = classes.get(class_id) if class_id else None
        if classroom is None:
            return None
        return {
            "id": str(classroom.id),
            "name": classroom.name,
            "grade_id": str(classroom.grade_id) if classroom.grade_id else None,
            "grade": grades.get(classroom.grade_id),
        }

    academic_history = []
    for result, assessment in result_rows:
        percentage = None
        if result.score is not None and assessment.max_score:
            percentage = round(float(result.score / assessment.max_score * 100), 2)
        academic_history.append({
            "school_id": str(assessment.school_id),
            "school": schools.get(assessment.school_id),
            "academic_year_id": str(assessment.academic_year_id),
            "academic_year": years.get(assessment.academic_year_id).name if years.get(assessment.academic_year_id) else None,
            "term_id": str(assessment.term_id),
            "term": terms.get(assessment.term_id).name if terms.get(assessment.term_id) else None,
            "class": class_payload(assessment.class_id),
            "subject_id": str(assessment.subject_id),
            "subject": subjects.get(assessment.subject_id),
            "assessment_id": str(assessment.id),
            "title": assessment.title,
            "assessment_type": assessment.assessment_type,
            "assessment_date": assessment.assessment_date.isoformat(),
            "max_score": float(assessment.max_score),
            "score": float(result.score) if result.score is not None else None,
            "percentage": percentage,
            "is_absent": result.is_absent,
            "is_excused": result.is_excused,
            "remarks": result.remarks,
        })

    return {
        "transfer": {
            "id": str(transfer.id),
            "reference_number": transfer.reference_number,
            "student_id": str(transfer.student_id),
            "source_school_id": str(transfer.source_school_id),
            "destination_school_id": str(transfer.destination_school_id),
            "accepted_at": transfer.accepted_at.isoformat() if transfer.accepted_at else None,
        },
        "learner": {
            "id": str(student.id),
            "admission_number": student.admission_number,
            "first_name": person.first_name if person else None,
            "last_name": person.last_name if person else None,
            "date_of_birth": person.date_of_birth.isoformat() if person and person.date_of_birth else None,
            "gender": getattr(person.gender, "value", person.gender) if person else None,
            "nationality": person.nationality if person else None,
        },
        "shared_source_schools": [
            {"school_id": str(school_id), "school": schools.get(school_id)}
            for school_id in sorted(school_ids, key=str)
        ],
        "enrollments": [
            {
                "id": str(row.id),
                "school_id": str(row.school_id),
                "school": schools.get(row.school_id),
                "class": class_payload(row.class_id),
                "academic_year_id": str(row.academic_year_id) if row.academic_year_id else None,
                "academic_year": years.get(row.academic_year_id).name if row.academic_year_id and years.get(row.academic_year_id) else row.academic_year,
                "term_id": str(row.term_id) if row.term_id else None,
                "term": terms.get(row.term_id).name if row.term_id and terms.get(row.term_id) else row.term,
                "start_date": row.start_date.isoformat() if row.start_date else None,
                "end_date": row.end_date.isoformat() if row.end_date else None,
                "status": row.status,
                "withdrawal_reason": row.withdrawal_reason,
                "transfer_destination": row.transfer_destination,
            }
            for row in enrollments
        ],
        "attendance": [
            {
                "id": str(row.id),
                "school_id": str(row.school_id),
                "school": schools.get(row.school_id),
                "date": row.attendance_date.isoformat(),
                "status": row.status,
                "remarks": row.remarks,
                "class": class_payload(row.classroom_id),
                "academic_year": years.get(row.academic_year_id).name if row.academic_year_id and years.get(row.academic_year_id) else None,
                "term": terms.get(row.term_id).name if row.term_id and terms.get(row.term_id) else None,
            }
            for row in attendance
        ],
        "academic_history": academic_history,
        "privacy": {
            "access": "read-only transfer-authorized longitudinal academic record",
            "finance_shared": False,
            "source_records_mutable_by_destination": False,
        },
    }
