from __future__ import annotations

import pytest

from app import product_dns


class FakePowerDNSClient:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], list[str]] = {}
        self.rectified: list[str] = []

    def get_zone(self, _zone: str) -> dict:
        rrsets = []
        for (name, rtype), values in self.records.items():
            rrsets.append(
                {
                    "name": f"{name}.",
                    "type": rtype,
                    "records": [{"content": value, "disabled": False} for value in values],
                }
            )
        return {"rrsets": rrsets}

    def replace_rrset(self, _zone: str, name: str, rtype: str, _ttl: int, values: list[str]) -> None:
        self.records[(name.rstrip(".").lower(), rtype)] = values

    def rectify_zone(self, zone: str) -> None:
        self.rectified.append(zone)


def test_reconcile_product_dns_registers_and_verifies_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakePowerDNSClient()
    monkeypatch.setattr(product_dns.settings, "bootstrap_public_ip", "204.12.205.224")
    monkeypatch.setattr(product_dns.settings, "powerdns_default_ttl", 300)
    monkeypatch.setattr(product_dns, "PowerDNSClient", lambda: client)

    record_type, target = product_dns.reconcile_product_dns(
        "ithute.co.ls",
        ["Tutor.Ithute.co.ls.", "api.pay.ithute.co.ls"],
    )

    assert (record_type, target) == ("A", "204.12.205.224")
    assert client.records[("tutor.ithute.co.ls", "A")] == ["204.12.205.224"]
    assert client.records[("api.pay.ithute.co.ls", "A")] == ["204.12.205.224"]
    assert client.rectified == ["ithute.co.ls"]


def test_reconcile_product_dns_requires_bootstrap_public_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(product_dns.settings, "bootstrap_public_ip", None)

    with pytest.raises(RuntimeError, match="BOOTSTRAP_PUBLIC_IP"):
        product_dns.reconcile_product_dns("ithute.co.ls", ["tutor.ithute.co.ls"])
