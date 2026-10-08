from app.services import dnssec_multi_resolver as multi


def test_two_authenticated_resolvers_agree(monkeypatch):
    monkeypatch.setattr(multi, "validating_resolver_check", lambda domain, resolver_ip: {"resolver": resolver_ip, "state": "validated"})
    result = multi.multi_resolver_dnssec_check("example.com")
    assert result["state"] == "validated"
    assert len(result["results"]) == 2


def test_disagreeing_resolvers_do_not_certify_dnssec(monkeypatch):
    monkeypatch.setattr(multi, "validating_resolver_check", lambda domain, resolver_ip: {"resolver": resolver_ip, "state": "validated" if resolver_ip == "1.1.1.1" else "unverified"})
    assert multi.multi_resolver_dnssec_check("example.com")["state"] == "inconsistent"


def test_servfail_is_possible_failure_not_proof(monkeypatch):
    monkeypatch.setattr(multi, "validating_resolver_check", lambda domain, resolver_ip: {"resolver": resolver_ip, "state": "failure"})
    result = multi.multi_resolver_dnssec_check("example.com")
    assert result["state"] == "possible_failure"
    assert result["read_only"] is True
