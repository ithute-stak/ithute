from app.services.mail_trust import authentication_evidence, inspect_urls, trusted_sender_evidence


def _message(**overrides):
    payload = {
        "from": "Ithute Security <auth@ithute.co.ls>",
        "subject": "Reset your Ithute password",
        "body_text": "Use https://ithute.co.ls/reset-password#token=example",
        "authentication_results": (
            "mx.ithute.co.ls; spf=pass smtp.mailfrom=ithute.co.ls; "
            "dkim=pass header.d=ithute.co.ls; dmarc=pass header.from=ithute.co.ls"
        ),
        "received_spf": "pass (sender SPF authorized)",
    }
    payload.update(overrides)
    return payload


def test_registered_sender_requires_authentication_before_verification():
    evidence = trusted_sender_evidence(
        _message(authentication_results="", received_spf="")
    )

    assert evidence["registry_match"] is True
    assert evidence["verified"] is False
    assert evidence["state"] == "registry_sender_unverified"


def test_authenticated_auth_sender_with_ithute_link_is_verified():
    evidence = trusted_sender_evidence(_message())

    assert evidence["verified"] is True
    assert evidence["state"] == "verified_system_sender"
    assert evidence["authentication"]["spf"] == "pass"
    assert evidence["authentication"]["dkim"] == "pass"
    assert evidence["authentication"]["dmarc"] == "pass"
    assert evidence["url_intelligence"]["suspicious_count"] == 0


def test_registered_sender_authentication_failure_is_high_signal():
    evidence = trusted_sender_evidence(
        _message(
            authentication_results=(
                "mx.ithute.co.ls; spf=fail; dkim=fail; dmarc=fail"
            ),
            received_spf="fail (not authorized)",
        )
    )

    assert evidence["verified"] is False
    assert evidence["state"] == "registry_sender_auth_failed"
    assert evidence["authentication"]["any_failure"] is True


def test_registered_sender_with_external_link_is_not_verified():
    evidence = trusted_sender_evidence(
        _message(body_text="Reset at https://ithute-security.example/reset-password")
    )

    assert evidence["verified"] is False
    assert evidence["url_intelligence"]["suspicious_count"] == 1
    assert "outside_trusted_sender_domains" in evidence["url_intelligence"]["items"][0]["reasons"]


def test_url_intelligence_flags_ip_and_http():
    result = inspect_urls(
        {"subject": "", "body_text": "Open http://192.0.2.50/login"},
        sender_domain="example.com",
    )

    assert result["suspicious_count"] == 1
    reasons = set(result["items"][0]["reasons"])
    assert "ip_literal_host" in reasons
    assert "not_https" in reasons


def test_authentication_evidence_does_not_invent_missing_results():
    evidence = authentication_evidence(
        {"from": "auth@ithute.co.ls", "authentication_results": "mx; arc=pass"}
    )

    assert evidence["spf"] == "unknown"
    assert evidence["dkim"] == "unknown"
    assert evidence["dmarc"] == "unknown"
    assert evidence["authenticated"] is False



def test_tenant_trusted_sender_requires_declared_authentication_and_links():
    registry = [{
        "name": "Example Bank",
        "category": "bank",
        "sender_addresses": ["alerts@bank.example"],
        "sender_domains": ["bank.example"],
        "allowed_link_domains": ["bank.example"],
        "require_spf": True,
        "require_dkim": True,
        "require_dmarc": True,
    }]
    evidence = trusted_sender_evidence(
        {
            "from": "Example Bank <alerts@bank.example>",
            "body_text": "Review https://secure.bank.example/account",
            "authentication_results": "mx; spf=pass; dkim=pass; dmarc=pass",
            "received_spf": "pass",
        },
        registry_entries=registry,
    )

    assert evidence["verified"] is True
    assert evidence["state"] == "verified_trusted_sender"
    assert evidence["registry_source"] == "tenant_registry"
    assert evidence["display_name"] == "Example Bank"


def test_tenant_trusted_sender_auth_failure_never_receives_trust_credit():
    registry = [{
        "name": "Payroll Partner",
        "category": "payroll",
        "sender_domains": ["payroll.example"],
        "allowed_link_domains": ["payroll.example"],
        "require_spf": True,
        "require_dkim": True,
        "require_dmarc": True,
    }]
    evidence = trusted_sender_evidence(
        {
            "from": "payroll@payroll.example",
            "body_text": "Open https://payroll.example/login",
            "authentication_results": "mx; spf=pass; dkim=fail; dmarc=pass",
        },
        registry_entries=registry,
    )

    assert evidence["verified"] is False
    assert evidence["state"] == "registry_sender_auth_failed"
    assert "dkim" in evidence["authentication_policy"]["missing_or_failed"]


def test_tenant_registry_cannot_weaken_first_party_ithute_policy():
    evidence = trusted_sender_evidence(
        _message(authentication_results="mx; spf=pass", received_spf="pass"),
        registry_entries=[{
            "name": "Override",
            "sender_domains": ["ithute.co.ls"],
            "allowed_link_domains": ["ithute.co.ls"],
            "require_spf": True,
            "require_dkim": False,
            "require_dmarc": False,
        }],
    )

    assert evidence["registry_source"] == "ithute_system_registry"
    assert evidence["verified"] is False
    assert set(evidence["authentication_policy"]["required"]) == {"spf", "dkim", "dmarc"}
