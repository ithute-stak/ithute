from app.services.dnssec_incidents import classify_dnssec_observation


def assessment(*, signing="complete", parent="complete", delegation="complete", resolver="validated"):
    readiness = {"steps": [{"key": "signing", "state": signing},
                           {"key": "parent", "state": parent},
                           {"key": "delegation", "state": delegation}]}
    return classify_dnssec_observation(readiness, {"state": resolver})


def test_authenticated_answer_is_healthy():
    assert assessment()["severity"] == "healthy"


def test_servfail_is_investigation_not_automatic_repair():
    result = assessment(resolver="failure")
    assert result["code"] == "DNS_RESOLVER_SERVFAIL"
    assert result["remediation"] == "investigate"


def test_parent_lookup_failure_is_not_reported_as_missing_ds():
    result = assessment(parent="blocked", resolver="error")
    assert result["severity"] == "unknown"
    assert result["remediation"] == "retry"


def test_missing_ds_is_not_claimed_cryptographically_verified():
    result = assessment(parent="pending", resolver="unverified")
    assert result["code"] == "DNSSEC_PARENT_DS_UNVERIFIED"


def test_disabled_signing_with_parent_ds_needs_investigation():
    result = assessment(signing="pending", parent="complete", resolver="unverified")
    assert result["severity"] == "warning"
    assert result["remediation"] == "investigate"



def test_authenticated_resolver_does_not_override_missing_parent_ds():
    result = assessment(parent="pending", resolver="validated")
    assert result["severity"] != "healthy"
    assert result["code"] == "DNSSEC_PARENT_DS_UNVERIFIED"


def test_authenticated_resolver_does_not_override_disabled_signing():
    result = assessment(signing="pending", resolver="validated")
    assert result["severity"] != "healthy"
    assert result["code"] == "DNSSEC_SIGNING_DISABLED"


def test_authenticated_resolver_does_not_override_inconclusive_delegation():
    result = assessment(delegation="pending", resolver="validated")
    assert result["severity"] == "unknown"
