from app.models.dnssec_incident_history import DnssecIncidentHistory, DnssecMonitorState


def test_dnssec_history_is_separate_from_general_domain_health():
    assert DnssecMonitorState.__tablename__ == "dnssec_monitor_states"
    assert DnssecIncidentHistory.__tablename__ == "dnssec_incident_history"
    assert "domain_health_monitor_states" not in {DnssecMonitorState.__tablename__, DnssecIncidentHistory.__tablename__}


def test_dnssec_history_has_tenant_and_domain_scoping():
    for model in (DnssecMonitorState, DnssecIncidentHistory):
        assert "tenant_id" in model.__table__.columns
        assert "domain_id" in model.__table__.columns


def test_dnssec_history_preserves_acknowledgement_and_recovery():
    columns = DnssecIncidentHistory.__table__.columns
    for name in ("opened_at", "acknowledged_at", "acknowledged_by", "recovered_at", "status"):
        assert name in columns
