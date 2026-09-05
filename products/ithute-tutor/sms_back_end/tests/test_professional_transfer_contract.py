from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_transfer_is_two_school_handover_not_instant_redeem():
    route = source("routes/student_transfers.py")
    assert '@router.post("/claim")' in route
    assert 'transfer.status = "under_review"' in route
    assert '@router.post("/{transfer_id}/accept")' in route
    assert '@router.post("/{transfer_id}/reject")' in route
    assert 'Transfer workflow upgraded: claim the code first' in route


def test_source_enrolment_moves_only_during_final_acceptance():
    route = source("routes/student_transfers.py")
    claim_section = route.split('@router.post("/claim")', 1)[1].split('@router.post("/redeem")', 1)[0]
    accept_section = route.split('@router.post("/{transfer_id}/accept")', 1)[1].split('@router.post("/{transfer_id}/reject")', 1)[0]
    assert 'source_enrollment.is_current = False' not in claim_section
    assert 'source_enrollment.is_current = False' in accept_section
    assert 'destination = StudentEnrollment(' in accept_section
    assert 'membership.is_active = True' in accept_section


def test_release_requires_recorded_transfer_authorization():
    route = source("routes/student_transfers.py")
    assert 'consent_confirmed: bool = False' in route
    assert 'if not payload.consent_confirmed' in route
    assert 'Confirm learner/guardian transfer authorization' in route


def test_receiving_school_must_review_packet_before_acceptance():
    route = source("routes/student_transfers.py")
    assert '@router.get("/{transfer_id}/review")' in route
    assert '"attendance_summary"' in route
    assert '"published_academic_summary"' in route
    assert 'records_verified: bool = False' in route
    assert 'if not payload.records_verified' in route
    assert 'Confirm that the receiving school reviewed the transfer packet' in route


def test_review_packet_is_revoked_after_terminal_decision():
    route = source("routes/student_transfers.py")
    assert 'if transfer.status != "under_review"' in route
    assert 'Admission-review packet access closes when the transfer leaves under-review status' in route


def test_final_acceptance_cannot_deactivate_source_before_effective_date():
    route = source("routes/student_transfers.py")
    accept_section = route.split('@router.post("/{transfer_id}/accept")', 1)[1].split('@router.post("/{transfer_id}/reject")', 1)[0]
    assert 'if payload.start_date > date.today()' in accept_section
    assert 'Final acceptance cannot occur before the effective transfer date' in accept_section


def test_rejection_and_cancellation_leave_source_enrolment_untouched():
    route = source("routes/student_transfers.py")
    reject_section = route.split('@router.post("/{transfer_id}/reject")', 1)[1].split('@router.post("/{transfer_id}/cancel")', 1)[0]
    cancel_section = route.split('@router.post("/{transfer_id}/cancel")', 1)[1].split('@router.get("")', 1)[0]
    assert 'source_enrollment.is_current = False' not in reject_section
    assert 'source_enrollment.is_current = False' not in cancel_section
    assert 'learner remains active at the releasing school' in reject_section
    assert 'learner remains active at the releasing school' in cancel_section


def test_transfer_has_reference_and_immutable_audit_events():
    model = source("database/multi_tenant_school_management/models/student_transfer.py")
    route = source("routes/student_transfers.py")
    assert 'reference_number = Column(String(40)' in model
    assert 'class StudentTransferEvent(Base):' in model
    assert '__tablename__ = "student_transfer_events"' in model
    assert 'event_type = Column(String(40)' in model
    assert 'def _event(' in route
    for event in ["released", "claimed", "accepted", "rejected", "cancelled"]:
        assert f'"{event}"' in route


def test_transfer_schema_upgrades_existing_rows_and_preserves_old_data():
    script = source("scripts/ensure_student_transfer_schema.py")
    assert 'ADD COLUMN IF NOT EXISTS reference_number' in script
    assert 'ADD COLUMN IF NOT EXISTS consent_confirmed' in script
    assert 'ADD COLUMN IF NOT EXISTS records_verified' in script
    assert "SET status = 'released' WHERE status = 'pending'" in script
    assert 'StudentTransferEvent.__table__' in script
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_student_transfers_reference_number' in script


def test_full_history_stays_post_acceptance_read_only_and_finance_free():
    route = source("routes/student_transfers.py")
    assert 'Full learner history becomes shareable only after the transfer is accepted' in route
    assert '"finance_shared": False' in route
    assert '"source_records_mutable_by_destination": False' in route
    assert 'FeeInvoice' not in route
    assert 'FeePayment' not in route
