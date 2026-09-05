import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.multi_tenant_school_management.models import Student, StudentAdmissionReservation


class StudentAdmissionNumberService:

    @staticmethod
    def generate_random_part() -> str:
        first_five = random.randint(0, 99999)
        last_digit = random.randint(1, 9)

        return f"{first_five:05d}{last_digit}"

    @staticmethod
    def student_admission_number_exists(
        db: Session,
        admission_number: str,
    ) -> bool:
        return (
            db.query(Student)
            .filter(Student.admission_number == admission_number)
            .first()
            is not None
        )

    @staticmethod
    def cleanup_expired_reservations(db: Session):
        now = datetime.now(timezone.utc)

        db.query(StudentAdmissionReservation).filter(
            StudentAdmissionReservation.is_used == False,
            StudentAdmissionReservation.expires_at < now,
        ).delete(synchronize_session=False)

        db.commit()

    @staticmethod
    def generate_admission_number(db: Session) -> str:
        year = date.today().year

        StudentAdmissionNumberService.cleanup_expired_reservations(db)

        for _ in range(100):
            random_part = StudentAdmissionNumberService.generate_random_part()
            admission_number = f"{year}{random_part}"

            if StudentAdmissionNumberService.student_admission_number_exists(
                db=db,
                admission_number=admission_number,
            ):
                continue

            reservation = StudentAdmissionReservation(
                admission_number=admission_number,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            )

            try:
                db.add(reservation)
                db.commit()
                return admission_number

            except IntegrityError:
                db.rollback()
                continue

        raise RuntimeError("Failed to generate unique admission number")

    @staticmethod
    def mark_admission_number_used(
        db: Session,
        admission_number: str,
    ):
        reservation = (
            db.query(StudentAdmissionReservation)
            .filter(
                StudentAdmissionReservation.admission_number == admission_number,
            )
            .first()
        )

        if reservation:
            reservation.is_used = True
            db.add(reservation)