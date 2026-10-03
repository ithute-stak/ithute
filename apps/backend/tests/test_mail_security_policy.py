from app.services import mail_security_policy


def test_mta_sts_policy_is_enforcing(monkeypatch):
    monkeypatch.setattr(mail_security_policy.settings, "mail_mta_sts_mode", "enforce")
    monkeypatch.setattr(mail_security_policy.settings, "mail_mta_sts_max_age_seconds", 604800)
    monkeypatch.setattr(mail_security_policy.settings, "mail_hostname", "mail.ithute.co.ls")
    policy = mail_security_policy.mta_sts_policy("example.com")
    assert "version: STSv1" in policy
    assert "mode: enforce" in policy
    assert "mx: mail.ithute.co.ls" in policy
    assert "max_age: 604800" in policy


def test_mta_sts_caddy_route_serves_only_well_known_policy(monkeypatch):
    monkeypatch.setattr(mail_security_policy.settings, "mail_mta_sts_mode", "enforce")
    monkeypatch.setattr(mail_security_policy.settings, "mail_mta_sts_max_age_seconds", 604800)
    monkeypatch.setattr(mail_security_policy.settings, "mail_hostname", "mail.ithute.co.ls")
    rendered = mail_security_policy.render_mta_sts_route("example.com")
    assert "mta-sts.example.com {" in rendered
    assert "/.well-known/mta-sts.txt" in rendered
    assert "version: STSv1" in rendered
    assert "respond 404" in rendered
