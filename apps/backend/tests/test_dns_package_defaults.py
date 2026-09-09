from types import SimpleNamespace
import uuid

from app.services import dns_defaults


class FakePowerDNS:
    def __init__(self, rrsets=None):
        self.zone = {"rrsets": list(rrsets or [])}
        self.replaced = []
        self.rectified = 0

    def get_zone(self, _name):
        return self.zone

    def replace_rrset(self, zone, name, rtype, ttl, contents):
        self.replaced.append((zone, name, rtype, ttl, list(contents)))
        key = (name.rstrip(".").lower(), rtype.upper())
        self.zone["rrsets"] = [
            row
            for row in self.zone["rrsets"]
            if (str(row.get("name", "")).rstrip(".").lower(), str(row.get("type", "")).upper()) != key
        ]
        self.zone["rrsets"].append(
            {
                "name": name.rstrip(".") + ".",
                "type": rtype,
                "ttl": ttl,
                "records": [{"content": value, "disabled": False} for value in contents],
            }
        )

    def rectify_zone(self, _name):
        self.rectified += 1


def domain(mail_enabled=True):
    return SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        ascii_name="example.co.ls",
        mail_enabled=mail_enabled,
    )


def profile(records):
    return dns_defaults.PackageDNSProfile(
        plan_id=str(uuid.uuid4()),
        plan_code="starter",
        plan_name="Starter",
        currency="LSL",
        monthly_price_minor=49000,
        included_domains=2,
        included_mailboxes=10,
        included_storage_mb=50_000,
        subscription_status="active",
        records=records,
    )


def test_desired_records_follow_package_mail_entitlement(monkeypatch):
    monkeypatch.setattr(dns_defaults.settings, "bootstrap_public_ip", "204.12.205.224")
    monkeypatch.setattr(dns_defaults.settings, "mail_hostname", "mail.ithute.co.ls")
    plan = SimpleNamespace(included_mailboxes=10)

    records = dns_defaults.desired_package_records(domain(mail_enabled=True), plan)
    purposes = {row["purpose"] for row in records}

    assert purposes == {"platform-web", "www-alias", "mail-routing", "spf", "dmarc"}
    assert next(row for row in records if row["purpose"] == "platform-web")["values"] == ["204.12.205.224"]
    assert next(row for row in records if row["purpose"] == "mail-routing")["values"] == ["10 mail.ithute.co.ls."]


def test_package_without_mailboxes_omits_mail_defaults(monkeypatch):
    monkeypatch.setattr(dns_defaults.settings, "bootstrap_public_ip", "204.12.205.224")
    plan = SimpleNamespace(included_mailboxes=0)

    records = dns_defaults.desired_package_records(domain(mail_enabled=True), plan)

    assert {row["purpose"] for row in records} == {"platform-web", "www-alias"}


def test_auto_generate_is_missing_only_and_preserves_txt(monkeypatch):
    wanted = [
        {"name": "example.co.ls", "type": "A", "values": ["204.12.205.224"], "purpose": "platform-web"},
        {"name": "example.co.ls", "type": "TXT", "values": ["v=spf1 mx -all"], "purpose": "spf"},
        {"name": "_dmarc.example.co.ls", "type": "TXT", "values": ["v=DMARC1; p=quarantine"], "purpose": "dmarc"},
    ]
    monkeypatch.setattr(dns_defaults, "package_dns_profile", lambda _db, _domain: profile(wanted))
    client = FakePowerDNS(
        [
            {"name": "example.co.ls.", "type": "A", "ttl": 3600, "records": [{"content": "192.0.2.9"}]},
            {"name": "example.co.ls.", "type": "TXT", "ttl": 3600, "records": [{"content": '"google-site-verification=abc"'}]},
        ]
    )

    result = dns_defaults.apply_package_dns_defaults(SimpleNamespace(), domain(), client=client)

    assert any(row["purpose"] == "platform-web" and row["reason"] == "existing_rrset" for row in result["skipped"])
    spf_write = next(row for row in client.replaced if row[2] == "TXT" and row[1] == "example.co.ls")
    assert '"google-site-verification=abc"' in spf_write[4]
    assert '"v=spf1 mx -all"' in spf_write[4]
    assert any(row["purpose"] == "dmarc" for row in result["generated"])
    assert client.rectified == 1


def test_auto_generate_second_run_is_idempotent(monkeypatch):
    wanted = [
        {"name": "example.co.ls", "type": "MX", "values": ["10 mail.ithute.co.ls."], "purpose": "mail-routing"},
        {"name": "example.co.ls", "type": "TXT", "values": ["v=spf1 mx -all"], "purpose": "spf"},
    ]
    monkeypatch.setattr(dns_defaults, "package_dns_profile", lambda _db, _domain: profile(wanted))
    client = FakePowerDNS()
    item = domain()

    first = dns_defaults.apply_package_dns_defaults(SimpleNamespace(), item, client=client)
    write_count = len(client.replaced)
    second = dns_defaults.apply_package_dns_defaults(SimpleNamespace(), item, client=client)

    assert len(first["generated"]) == 2
    assert len(client.replaced) == write_count
    assert second["generated"] == []
    assert len(second["skipped"]) == 2


def test_auto_generate_leaves_cname_conflict_untouched(monkeypatch):
    wanted = [
        {"name": "www.example.co.ls", "type": "CNAME", "values": ["example.co.ls."], "purpose": "www-alias"},
    ]
    monkeypatch.setattr(dns_defaults, "package_dns_profile", lambda _db, _domain: profile(wanted))
    client = FakePowerDNS(
        [{"name": "www.example.co.ls.", "type": "A", "ttl": 3600, "records": [{"content": "192.0.2.10"}]}]
    )

    result = dns_defaults.apply_package_dns_defaults(SimpleNamespace(), domain(), client=client)

    assert client.replaced == []
    assert result["skipped"][0]["reason"] == "cname_conflict"
