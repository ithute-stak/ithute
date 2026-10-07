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
