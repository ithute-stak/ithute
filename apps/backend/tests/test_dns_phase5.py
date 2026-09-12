from app.services.dns_phase5 import dns_templates
from app.services.powerdns import PowerDNSError


def test_phase5_templates_are_domain_aware():
    templates = {item.name: item for item in dns_templates("example.com")}
    assert {"website", "mail-readiness", "security-baseline"} <= set(templates)
    mx = next(record for record in templates["mail-readiness"].records if record["type"] == "MX")
    assert mx["contents"] == ["10 mail.example.com."]


def test_powerdns_error_exposes_status_code():
    error = PowerDNSError("not found", 404)
    assert error.status_code == 404
    assert str(error) == "not found"
