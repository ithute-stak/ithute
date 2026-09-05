from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_learning_material_keeps_owner_school_and_moderation_state():
    model = source("database/multi_tenant_school_management/models/learning_material.py")
    assert 'school_id = Column(' in model
    assert 'ForeignKey("schools.id", ondelete="CASCADE")' in model
    assert 'visibility = Column(' in model
    assert 'moderation_status = Column(' in model
    assert 'peer_approval_threshold = Column(' in model
    assert 'UniqueConstraint("material_id", "school_id"' in model


def test_public_library_only_exposes_approved_active_public_material():
    route = source("routes/learning_exchange.py")
    assert 'LearningMaterial.visibility == "public"' in route
    assert 'LearningMaterial.moderation_status == "approved"' in route
    assert 'LearningMaterial.is_active.is_(True)' in route
    assert 'source_school' in route


def test_publishing_school_cannot_peer_approve_itself_and_each_school_approves_once():
    route = source("routes/learning_exchange.py")
    model = source("database/multi_tenant_school_management/models/learning_material.py")
    assert 'if item.school_id == context.school_id' in route
    assert 'The publishing school cannot approve its own public material' in route
    assert 'LearningMaterialApproval.school_id == context.school_id' in route
    assert 'uq_learning_material_approval_school' in model


def test_platform_or_peer_approval_can_publish_material():
    route = source("routes/learning_exchange.py")
    assert 'item.approval_source = "peer"' in route
    assert 'item.approval_source = "platform"' in route
    assert 'count >= item.peer_approval_threshold' in route
    assert '_role(user) != "super_admin"' in route


def test_editing_material_revokes_previous_public_approval():
    route = source("routes/learning_exchange.py")
    assert 'def _reset_public_approval' in route
    assert 'LearningMaterialApproval.material_id == item.id' in route
    assert 'item.moderation_status = "draft"' in route
    assert 'item.published_at = None' in route
    assert '_reset_public_approval(db, item)' in route


def test_peer_and_platform_review_queues_are_separate():
    route = source("routes/learning_review.py")
    assert 'LearningMaterial.school_id != context.school_id' in route
    assert 'PEER_APPROVERS' in route
    assert 'platform-review-queue' in route
    assert '_role(user) != "super_admin"' in route


def test_transfer_records_require_accepted_transfer_and_party_authorization():
    route = source("routes/student_transfers.py")
    assert 'transfer.status != "accepted"' in route
    assert 'context.school_id not in' in route
    assert 'transfer.source_school_id' in route
    assert 'transfer.destination_school_id' in route
    assert 'This school is not a party to this learner transfer' in route


def test_receiving_school_gets_prior_transfer_lineage_not_global_database_access():
    route = source("routes/student_transfers.py")
    assert 'StudentTransfer.student_id == transfer.student_id' in route
    assert 'StudentTransfer.status == "accepted"' in route
    assert 'StudentTransfer.accepted_at <= transfer.accepted_at' in route
    assert 'school_ids = {row.source_school_id for row in lineage}' in route
    assert 'StudentEnrollment.school_id.in_(school_ids)' in route
    assert 'StudentAttendance.school_id.in_(school_ids)' in route


def test_transfer_dossier_shares_only_published_academic_results_and_no_finance():
    route = source("routes/student_transfers.py")
    assert 'Assessment.is_published.is_(True)' in route
    assert 'Assessment.school_id.in_(school_ids)' in route
    assert '"finance_shared": False' in route
    assert '"source_records_mutable_by_destination": False' in route
    assert 'FeeInvoice' not in route
    assert 'FeePayment' not in route


def test_cross_school_routers_are_mounted_and_schema_is_provisioned():
    main = source("main.py")
    entrypoint = source("docker-entrypoint.sh")
    assert 'app.include_router(student_transfers.router)' in main
    assert 'app.include_router(learning_exchange.router)' in main
    assert 'app.include_router(learning_review.router)' in main
    assert 'ensure_learning_exchange_schema.py' in entrypoint
    assert 'ensure_student_transfer_schema.py' in entrypoint
