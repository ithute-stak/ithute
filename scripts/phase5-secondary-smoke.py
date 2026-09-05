from __future__ import annotations

import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import dns.resolver

PRIMARY_API = "http://powerdns:8081/api/v1"
SECONDARY_API = "http://powerdns-secondary:8081/api/v1"
PRIMARY_KEY = os.environ.get("POWERDNS_API_KEY", "development-powerdns-api-key-change-me")
SECONDARY_KEY = "phase5-secondary-api-key-change-me"
SERVER = "localhost"
ZONE = "phase5-transfer.test."
ZONE_ID = quote(ZONE, safe="")


def request(base: str, key: str, method: str, path: str, payload=None, expected=(200, 201, 204)):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=body, method=method, headers={"X-API-Key": key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=8) as response:
            raw = response.read()
            if response.status not in expected:
                raise RuntimeError(f"unexpected HTTP {response.status} for {method} {path}")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"PowerDNS HTTP {exc.code} for {method} {path}: {detail}") from exc


def delete_if_present(base: str, key: str):
    req = Request(base + f"/servers/{SERVER}/zones/{ZONE_ID}", method="DELETE", headers={"X-API-Key": key})
    try:
        with urlopen(req, timeout=8):
            pass
    except HTTPError as exc:
        if exc.code != 404:
            raise


def query(server: str, name: str, rtype: str):
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [server]
    resolver.port = 53
    resolver.timeout = 2
    resolver.lifetime = 4
    return [item.to_text() for item in resolver.resolve(name, rtype)]


def main():
    delete_if_present(SECONDARY_API, SECONDARY_KEY)
    delete_if_present(PRIMARY_API, PRIMARY_KEY)

    primary_zone = request(PRIMARY_API, PRIMARY_KEY, "POST", f"/servers/{SERVER}/zones", {
        "name": ZONE,
        "kind": "Master",
        "nameservers": ["ns1.phase5-transfer.test.", "ns2.phase5-transfer.test."],
        "api_rectify": True,
    })
    assert primary_zone["kind"] == "Master"

    request(PRIMARY_API, PRIMARY_KEY, "PATCH", f"/servers/{SERVER}/zones/{ZONE_ID}", {
        "rrsets": [{
            "name": "www." + ZONE,
            "type": "A",
            "ttl": 60,
            "changetype": "REPLACE",
            "records": [{"content": "192.0.2.55", "disabled": False}],
        }]
    }, expected=(204,))

    request(PRIMARY_API, PRIMARY_KEY, "PUT", f"/servers/{SERVER}/zones/{ZONE_ID}", {"dnssec": True, "api_rectify": True}, expected=(204,))
    signed = request(PRIMARY_API, PRIMARY_KEY, "GET", f"/servers/{SERVER}/zones/{ZONE_ID}") or {}
    assert signed.get("dnssec") is True, f"DNSSEC was not enabled: {signed}"
    keys = request(PRIMARY_API, PRIMARY_KEY, "GET", f"/servers/{SERVER}/zones/{ZONE_ID}/cryptokeys") or []
    assert keys and any(key.get("ds") for key in keys), "DNSSEC did not produce a DS record"
    assert query("172.31.55.10", ZONE, "DNSKEY"), "primary does not serve DNSKEY"

    secondary_zone = request(SECONDARY_API, SECONDARY_KEY, "POST", f"/servers/{SERVER}/zones", {
        "name": ZONE,
        "kind": "Slave",
        "masters": ["172.31.55.10"],
    })
    assert secondary_zone["kind"] == "Slave"
    request(SECONDARY_API, SECONDARY_KEY, "PUT", f"/servers/{SERVER}/zones/{ZONE_ID}/axfr-retrieve", {"primary": "172.31.55.10"})

    deadline = time.time() + 20
    while True:
        try:
            values = query("172.31.55.11", "www." + ZONE, "A")
            if "192.0.2.55" in values:
                break
        except Exception:
            pass
        if time.time() >= deadline:
            raise RuntimeError("secondary did not answer transferred A record")
        time.sleep(1)

    request(PRIMARY_API, PRIMARY_KEY, "PATCH", f"/servers/{SERVER}/zones/{ZONE_ID}", {
        "rrsets": [{
            "name": "www." + ZONE,
            "type": "A",
            "ttl": 60,
            "changetype": "REPLACE",
            "records": [{"content": "192.0.2.56", "disabled": False}],
        }]
    }, expected=(204,))
    request(SECONDARY_API, SECONDARY_KEY, "PUT", f"/servers/{SERVER}/zones/{ZONE_ID}/axfr-retrieve", {"primary": "172.31.55.10"})
    deadline = time.time() + 20
    while True:
        try:
            values = query("172.31.55.11", "www." + ZONE, "A")
            if "192.0.2.56" in values:
                break
        except Exception:
            pass
        if time.time() >= deadline:
            raise RuntimeError("secondary did not refresh changed A record")
        time.sleep(1)

    primary_soa = query("172.31.55.10", ZONE, "SOA")[0]
    secondary_soa = query("172.31.55.11", ZONE, "SOA")[0]
    assert primary_soa == secondary_soa, "primary and secondary SOA data differ"

    delete_if_present(SECONDARY_API, SECONDARY_KEY)
    delete_if_present(PRIMARY_API, PRIMARY_KEY)
    print("Phase 5 DNSSEC + secondary transfer smoke PASSED.")


if __name__ == "__main__":
    main()
