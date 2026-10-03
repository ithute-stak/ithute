from app.services.security_event_rules import audit_security_severity


def test_high_risk_actions_are_promoted():
    assert audit_security_severity("mail_node.failover.complete") == "critical"
    assert audit_security_severity("api_key.create") == "high"
    assert audit_security_severity("webmail.login.failed") == "medium"


def test_normal_business_actions_do_not_create_security_noise():
    assert audit_security_severity("finance.invoice.create") is None
