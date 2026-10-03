from app.services import mail_transport_security


def test_mta_sts_policy_is_strictly_formatted(monkeypatch):
    monkeypatch.setattr(mail_transport_security.settings, "mail_hostname", "mail.ithute.co.ls")
    monkeypatch.setattr(mail_transport_security.settings, "mail_mta_sts_mode", "enforce")
    monkeypatch.setattr(mail_transport_security.settings, "mail_mta_sts_max_age_seconds", 604800)

    policy = mail_transport_security.mta_sts_policy("Example.COM")

    assert policy == (
        "version: STSv1\n"
        "mode: enforce\n"
        "mx: mail.ithute.co.ls\n"
        "max_age: 604800\n"
    )


def test_transport_records_require_real_edge_before_mta_sts(monkeypatch):
    monkeypatch.setattr(mail_transport_security.settings, "mail_mta_sts_enabled", True)
    monkeypatch.setattr(mail_transport_security.settings, "bootstrap_public_ip", None)
    monkeypatch.setattr(mail_transport_security.settings, "mail_tls_report_address", "tls-reports@ithute.co.ls")

    records = mail_transport_security.transport_security_records("example.com")
    purposes = {item["purpose"] for item in records}

    assert "mta-sts" not in purposes
    assert "mta-sts-host" not in purposes
    assert "tls-rpt" in purposes


def test_transport_records_include_policy_host_activation_and_tls_reporting(monkeypatch):
    monkeypatch.setattr(mail_transport_security.settings, "mail_mta_sts_enabled", True)
    monkeypatch.setattr(mail_transport_security.settings, "bootstrap_public_ip", "203.0.113.25")
    monkeypatch.setattr(mail_transport_security.settings, "mail_tls_report_address", "tls-reports@ithute.co.ls")
    monkeypatch.setattr(mail_transport_security.settings, "mail_hostname", "mail.ithute.co.ls")
    monkeypatch.setattr(mail_transport_security.settings, "mail_mta_sts_mode", "testing")
    monkeypatch.setattr(mail_transport_security.settings, "mail_mta_sts_max_age_seconds", 604800)

    records = {item["purpose"]: item for item in mail_transport_security.transport_security_records("example.com")}

    assert records["mta-sts-host"]["name"] == "mta-sts.example.com"
    assert records["mta-sts-host"]["value"] == "203.0.113.25"
    assert records["mta-sts"]["name"] == "_mta-sts.example.com"
    assert records["mta-sts"]["value"].startswith("v=STSv1; id=")
    assert records["tls-rpt"]["name"] == "_smtp._tls.example.com"
    assert records["tls-rpt"]["value"] == "v=TLSRPTv1; rua=mailto:tls-reports@ithute.co.ls"
