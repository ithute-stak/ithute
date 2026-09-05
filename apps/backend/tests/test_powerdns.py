import pytest

from app.services.powerdns import PowerDNSClient, normalize_record_name, validate_record


def test_normalize_record_names():
    assert normalize_record_name("example.com", "@") == "example.com"
    assert normalize_record_name("example.com", "www") == "www.example.com"
    assert normalize_record_name("example.com", "www.example.com.") == "www.example.com"


def test_validate_a_and_aaaa():
    assert validate_record("example.com", "www", "A", ["192.0.2.10"])[0] == "www.example.com"
    assert validate_record("example.com", "www", "AAAA", ["2001:db8::10"])[1] == "AAAA"
    with pytest.raises(ValueError):
        validate_record("example.com", "www", "A", ["2001:db8::1"])


def test_reject_unsupported_and_bad_cname():
    with pytest.raises(ValueError):
        validate_record("example.com", "www", "PTR", ["host.example.com."])
    with pytest.raises(ValueError):
        validate_record("example.com", "@", "CNAME", ["other.example.net."])
    with pytest.raises(ValueError):
        validate_record("example.com", "www", "CNAME", ["one.example.net.", "two.example.net."])


def test_record_set_limits():
    with pytest.raises(ValueError):
        validate_record("example.com", "www", "TXT", [])
    with pytest.raises(ValueError):
        validate_record("example.com", "www", "TXT", ["x"] * 101)


class FakeAuthorityClient(PowerDNSClient):
    def __init__(self, zone):
        self.zone = zone
        self.replacements = []
        self.rectified = []

    def get_zone(self, name: str) -> dict:
        return self.zone

    def replace_rrset(self, zone: str, name: str, rtype: str, ttl: int, contents: list[str]) -> None:
        self.replacements.append((zone, name, rtype, ttl, contents))

    def rectify_zone(self, name: str) -> None:
        self.rectified.append(name)


def test_reconcile_authority_replaces_powerdns_fallback_soa():
    client = FakeAuthorityClient(
        {
            "name": "ithute.co.ls.",
            "rrsets": [
                {
                    "name": "ithute.co.ls.",
                    "type": "NS",
                    "records": [
                        {"content": "ns1.ithute.co.ls."},
                        {"content": "ns2.ithute.co.ls."},
                    ],
                },
                {
                    "name": "ithute.co.ls.",
                    "type": "SOA",
                    "records": [
                        {
                            "content": "a.misconfigured.dns.server.invalid. hostmaster.ithute.co.ls. 2026090116 10800 3600 604800 3600"
                        }
                    ],
                },
            ],
        }
    )

    client.reconcile_authority("ithute.co.ls", ["ns1.ithute.co.ls", "ns2.ithute.co.ls"])

    assert len(client.replacements) == 1
    zone, name, rtype, _, contents = client.replacements[0]
    assert zone == "ithute.co.ls"
    assert name == "ithute.co.ls."
    assert rtype == "SOA"
    parts = contents[0].split()
    assert parts[0] == "ns1.ithute.co.ls."
    assert parts[1] == "hostmaster.ithute.co.ls."
    assert int(parts[2]) > 2026090116
    assert parts[3:] == ["10800", "3600", "604800", "3600"]
    assert client.rectified == ["ithute.co.ls"]


def test_reconcile_authority_replaces_mismatched_ns_and_soa():
    client = FakeAuthorityClient(
        {
            "name": "customer.co.ls.",
            "rrsets": [
                {
                    "name": "customer.co.ls.",
                    "type": "NS",
                    "records": [
                        {"content": "old1.provider.test."},
                        {"content": "old2.provider.test."},
                    ],
                },
                {
                    "name": "customer.co.ls.",
                    "type": "SOA",
                    "records": [
                        {"content": "old1.provider.test. hostmaster.customer.co.ls. 2026090101 10800 3600 604800 3600"}
                    ],
                },
            ],
        }
    )

    client.reconcile_authority("customer.co.ls", ["ns1.ithute.co.ls", "ns2.ithute.co.ls"])

    changed_types = [item[2] for item in client.replacements]
    assert changed_types == ["NS", "SOA"]
    ns_contents = client.replacements[0][4]
    assert ns_contents == ["ns1.ithute.co.ls.", "ns2.ithute.co.ls."]
    assert client.replacements[1][4][0].startswith("ns1.ithute.co.ls. hostmaster.customer.co.ls.")
