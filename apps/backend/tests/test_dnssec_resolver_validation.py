import dns.flags
import dns.message
import dns.rcode
import dns.rdatatype

from app.services import dnssec_resolver_validation as checks


def _response(ad=False, rcode=dns.rcode.NOERROR):
    response = dns.message.make_response(dns.message.make_query("example.com.", dns.rdatatype.SOA))
    response.set_rcode(rcode)
    if ad:
        response.flags |= dns.flags.AD
    return response


def test_validating_resolver_authenticated(monkeypatch):
    monkeypatch.setattr(checks.dns.query, "udp", lambda *args, **kwargs: _response(ad=True))
    result = checks.validating_resolver_check("example.com")
    assert result["state"] == "validated"
    assert result["authenticated"] is True


def test_unsigned_response_is_unverified(monkeypatch):
    monkeypatch.setattr(checks.dns.query, "udp", lambda *args, **kwargs: _response())
    assert checks.validating_resolver_check("example.com")["state"] == "unverified"


def test_servfail_is_not_claimed_as_cryptographic_proof(monkeypatch):
    monkeypatch.setattr(checks.dns.query, "udp", lambda *args, **kwargs: _response(rcode=dns.rcode.SERVFAIL))
    assert checks.validating_resolver_check("example.com")["state"] == "failure"


def test_timeout_remains_unknown(monkeypatch):
    import dns.exception
    def timeout(*args, **kwargs):
        raise dns.exception.Timeout()
    monkeypatch.setattr(checks.dns.query, "udp", timeout)
    assert checks.validating_resolver_check("example.com")["state"] == "error"
