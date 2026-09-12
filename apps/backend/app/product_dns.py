from __future__ import annotations

import argparse
from ipaddress import ip_address

from app.core.config import settings
from app.services.powerdns import PowerDNSClient


def reconcile_product_dns(zone_name: str, hosts: list[str]) -> tuple[str, str]:
    """Reconcile product hostnames to the configured public IP and verify them."""
    cleaned_hosts = [host.strip().rstrip(".").lower() for host in hosts if host.strip()]
    if not cleaned_hosts:
        raise ValueError("At least one product hostname is required")

    if not settings.bootstrap_public_ip:
        raise RuntimeError("BOOTSTRAP_PUBLIC_IP is required to register product routes")

    address = ip_address(settings.bootstrap_public_ip.strip())
    record_type = "A" if address.version == 4 else "AAAA"
    target = str(address)
    client = PowerDNSClient()

    client.get_zone(zone_name)
    for hostname in cleaned_hosts:
        client.replace_rrset(
            zone_name,
            hostname,
            record_type,
            settings.powerdns_default_ttl,
            [target],
        )
    client.rectify_zone(zone_name)

    zone = client.get_zone(zone_name)
    rrsets = zone.get("rrsets", []) if isinstance(zone, dict) else []
    expected = set(cleaned_hosts)
    observed: dict[str, list[str]] = {}
    for rrset in rrsets:
        if not isinstance(rrset, dict) or str(rrset.get("type", "")).upper() != record_type:
            continue
        name = str(rrset.get("name", "")).rstrip(".").lower()
        if name not in expected:
            continue
        values = [
            str(record.get("content", "")).strip()
            for record in rrset.get("records", [])
            if isinstance(record, dict) and not record.get("disabled", False)
        ]
        observed[name] = values

    missing = [hostname for hostname in cleaned_hosts if target not in observed.get(hostname, [])]
    if missing:
        raise RuntimeError(f"PowerDNS verification failed for: {', '.join(missing)}")

    return record_type, target


def main() -> None:
    parser = argparse.ArgumentParser(description="Register and verify Ithute product DNS routes")
    parser.add_argument("--zone", default="ithute.co.ls", help="Authoritative PowerDNS zone")
    parser.add_argument("--host", action="append", dest="hosts", required=True, help="Hostname to register; repeat for multiple hosts")
    args = parser.parse_args()

    record_type, target = reconcile_product_dns(args.zone, args.hosts)
    for hostname in args.hosts:
        print(f"DNS registered: {hostname.rstrip('.').lower()} {record_type} {target}")


if __name__ == "__main__":
    main()
