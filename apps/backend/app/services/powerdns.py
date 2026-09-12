from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.config import settings


class PowerDNSError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PowerDNSResult:
    status: int
    data: dict | list | None


def _clean_nameservers(nameservers: list[str]) -> list[str]:
    cleaned: list[str] = []
    for nameserver in nameservers:
        value = nameserver.strip().rstrip(".").lower()
        if not value or "." not in value:
            raise ValueError("Authoritative nameservers must be fully-qualified hostnames")
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) < 2:
        raise ValueError("At least two distinct authoritative nameservers are required")
    return cleaned


def _next_soa_serial(current: int | None) -> int:
    daily_floor = int(datetime.now(timezone.utc).strftime("%Y%m%d00"))
    return max(daily_floor, (current or 0) + 1)


class PowerDNSClient:
    """Small, dependency-free client for the PowerDNS Authoritative HTTP API."""

    def __init__(self) -> None:
        self.base = settings.powerdns_api_url.rstrip("/")
        self.server_id = quote(settings.powerdns_server_id, safe="")
        self.api_key = settings.powerdns_api_key
        self.timeout = settings.powerdns_api_timeout_seconds

    def _request(self, method: str, path: str, payload: dict | None = None, ok: tuple[int, ...] = (200,)) -> PowerDNSResult:
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(
            f"{self.base}{path}",
            data=body,
            method=method,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read()
                data = json.loads(raw) if raw else None
                if response.status not in ok:
                    raise PowerDNSError(f"PowerDNS returned HTTP {response.status}", response.status)
                return PowerDNSResult(response.status, data)
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise PowerDNSError(f"PowerDNS HTTP {exc.code}: {detail}", exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise PowerDNSError(f"PowerDNS unavailable: {exc}") from exc

    def _zone_id(self, name: str) -> str:
        return quote(name.rstrip(".") + ".", safe="")

    def health(self) -> dict:
        return self._request("GET", f"/servers/{self.server_id}").data or {}

    def get_zone(self, name: str) -> dict:
        return self._request("GET", f"/servers/{self.server_id}/zones/{self._zone_id(name)}").data or {}

    def create_zone_with_nameservers(self, name: str, nameservers: list[str]) -> dict:
        fqdn = name.rstrip(".") + "."
        cleaned = _clean_nameservers(nameservers)
        payload = {
            "name": fqdn,
            "kind": "Master",
            "nameservers": [value + "." for value in cleaned],
            "api_rectify": True,
        }
        self._request("POST", f"/servers/{self.server_id}/zones", payload, (201,))
        return self.reconcile_authority(name, cleaned)

    def create_zone(self, name: str) -> dict:
        return self.create_zone_with_nameservers(name, [settings.nameserver_1, settings.nameserver_2])

    def reconcile_authority(self, name: str, nameservers: list[str] | None = None) -> dict:
        """Keep apex NS and SOA authority metadata aligned with platform identity.

        PowerDNS can otherwise create an SOA with its fallback
        `a.misconfigured.dns.server.invalid` MNAME. We explicitly own these
        authority records so every managed zone publishes a valid primary NS
        and hostmaster RNAME. The SOA serial only advances when authority data
        actually changes.
        """
        zone_name = name.rstrip(".").lower()
        apex = zone_name + "."
        cleaned = _clean_nameservers(nameservers or [settings.nameserver_1, settings.nameserver_2])
        zone = self.get_zone(zone_name)
        rrsets = zone.get("rrsets") if isinstance(zone, dict) else None
        rrsets = rrsets if isinstance(rrsets, list) else []

        current_ns: set[str] = set()
        current_soa: str | None = None
        for rrset in rrsets:
            if not isinstance(rrset, dict) or str(rrset.get("name", "")).rstrip(".").lower() != zone_name:
                continue
            rtype = str(rrset.get("type", "")).upper()
            records = rrset.get("records") if isinstance(rrset.get("records"), list) else []
            if rtype == "NS":
                current_ns = {
                    str(record.get("content", "")).strip().rstrip(".").lower()
                    for record in records
                    if isinstance(record, dict) and str(record.get("content", "")).strip()
                }
            elif rtype == "SOA" and records:
                first = records[0]
                if isinstance(first, dict):
                    current_soa = str(first.get("content", "")).strip() or None

        desired_ns = set(cleaned)
        primary = cleaned[0] + "."
        rname = f"hostmaster.{zone_name}."
        soa_parts = current_soa.split() if current_soa else []
        current_serial: int | None = None
        if len(soa_parts) >= 3:
            try:
                current_serial = int(soa_parts[2])
            except ValueError:
                current_serial = None

        soa_identity_ok = (
            len(soa_parts) >= 7
            and soa_parts[0].rstrip(".").lower() == cleaned[0]
            and soa_parts[1].rstrip(".").lower() == f"hostmaster.{zone_name}"
            and soa_parts[3:] == ["10800", "3600", "604800", "3600"]
        )
        ns_changed = current_ns != desired_ns
        soa_changed = not soa_identity_ok
        if not ns_changed and not soa_changed:
            return zone

        serial = _next_soa_serial(current_serial)
        soa_content = f"{primary} {rname} {serial} 10800 3600 604800 3600"
        ttl = settings.powerdns_default_ttl
        if ns_changed:
            self.replace_rrset(zone_name, apex, "NS", ttl, [value + "." for value in cleaned])
        self.replace_rrset(zone_name, apex, "SOA", ttl, [soa_content])
        self.rectify_zone(zone_name)
        return self.get_zone(zone_name)

    def update_zone(self, name: str, payload: dict) -> None:
        self._request("PUT", f"/servers/{self.server_id}/zones/{self._zone_id(name)}", payload, ok=(204,))

    def set_dnssec(self, name: str, enabled: bool) -> dict:
        self.update_zone(name, {"dnssec": enabled, "api_rectify": enabled})
        return self.get_zone(name)

    def list_cryptokeys(self, name: str) -> list[dict]:
        data = self._request("GET", f"/servers/{self.server_id}/zones/{self._zone_id(name)}/cryptokeys").data
        return data if isinstance(data, list) else []

    def rectify_zone(self, name: str) -> None:
        self._request("PUT", f"/servers/{self.server_id}/zones/{self._zone_id(name)}/rectify", ok=(200,))

    def delete_zone(self, name: str) -> None:
        self._request("DELETE", f"/servers/{self.server_id}/zones/{self._zone_id(name)}", ok=(204,))

    def replace_rrset(self, zone: str, name: str, rtype: str, ttl: int, contents: list[str]) -> None:
        payload = {"rrsets": [{"name": name.rstrip(".") + ".", "type": rtype, "ttl": ttl, "changetype": "REPLACE", "records": [{"content": c, "disabled": False} for c in contents]}]}
        self._request("PATCH", f"/servers/{self.server_id}/zones/{self._zone_id(zone)}", payload, ok=(204,))

    def delete_rrset(self, zone: str, name: str, rtype: str) -> None:
        payload = {"rrsets": [{"name": name.rstrip(".") + ".", "type": rtype, "changetype": "DELETE"}]}
        self._request("PATCH", f"/servers/{self.server_id}/zones/{self._zone_id(zone)}", payload, ok=(204,))


def normalize_record_name(zone: str, name: str) -> str:
    zone = zone.rstrip(".").lower()
    value = name.strip().rstrip(".").lower()
    if value in {"", "@"}:
        return zone
    if value == zone or value.endswith("." + zone):
        return value
    return f"{value}.{zone}"


def _canonical_hostname(zone: str, value: str, *, allow_root: bool = False) -> str:
    """Convert a customer-friendly hostname into canonical PowerDNS RDATA form."""
    raw = value.strip()
    if raw == ".":
        if allow_root:
            return raw
        raise ValueError("Record target must be a hostname")
    target = raw.rstrip(".").lower()
    if not target:
        raise ValueError("Record target must be a hostname")
    if target == "@":
        target = zone.rstrip(".").lower()
    elif "." not in target:
        target = f"{target}.{zone.rstrip('.').lower()}"
    if any(not label or len(label) > 63 for label in target.split(".")) or len(target) > 253:
        raise ValueError("Record target must be a valid hostname")
    return target + "."


def _normalize_mx(zone: str, value: str) -> str:
    parts = value.split()
    if len(parts) != 2:
        raise ValueError("MX values must use: priority hostname")
    try:
        priority = int(parts[0])
    except ValueError as exc:
        raise ValueError("MX priority must be a number between 0 and 65535") from exc
    if not 0 <= priority <= 65535:
        raise ValueError("MX priority must be a number between 0 and 65535")
    return f"{priority} {_canonical_hostname(zone, parts[1], allow_root=True)}"


def _normalize_srv(zone: str, value: str) -> str:
    parts = value.split()
    if len(parts) != 4:
        raise ValueError("SRV values must use: priority weight port target")
    try:
        priority, weight, port = (int(parts[index]) for index in range(3))
    except ValueError as exc:
        raise ValueError("SRV priority, weight and port must be numbers") from exc
    if not all(0 <= number <= 65535 for number in (priority, weight, port)):
        raise ValueError("SRV priority, weight and port must be between 0 and 65535")
    return f"{priority} {weight} {port} {_canonical_hostname(zone, parts[3], allow_root=True)}"


def _normalize_txt(value: str) -> str:
    raw = value.strip()
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        return raw
    escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def validate_record(zone: str, name: str, rtype: str, contents: list[str]) -> tuple[str, str, list[str]]:
    fqdn = normalize_record_name(zone, name)
    zone = zone.rstrip(".").lower()
    if fqdn != zone and not fqdn.endswith("." + zone):
        raise ValueError("Record name must be inside the managed zone")
    rtype = rtype.upper()
    allowed = {"A", "AAAA", "CNAME", "MX", "TXT", "CAA", "SRV"}
    if rtype not in allowed:
        raise ValueError(f"Unsupported record type: {rtype}")
    if not contents or len(contents) > 100:
        raise ValueError("Record set must contain between 1 and 100 values")
    cleaned = [str(value).strip() for value in contents]
    if any(not value or len(value) > 4096 for value in cleaned):
        raise ValueError("Invalid DNS record value")
    if rtype == "A":
        for value in cleaned:
            if ipaddress.ip_address(value).version != 4:
                raise ValueError("A records require IPv4 addresses")
    if rtype == "AAAA":
        for value in cleaned:
            if ipaddress.ip_address(value).version != 6:
                raise ValueError("AAAA records require IPv6 addresses")
    if rtype == "CNAME":
        if len(cleaned) != 1 or fqdn == zone:
            raise ValueError("CNAME requires one value and cannot be used at the zone apex")
        cleaned = [_canonical_hostname(zone, cleaned[0])]
    elif rtype == "MX":
        cleaned = [_normalize_mx(zone, value) for value in cleaned]
    elif rtype == "SRV":
        cleaned = [_normalize_srv(zone, value) for value in cleaned]
    elif rtype == "TXT":
        cleaned = [_normalize_txt(value) for value in cleaned]
    return fqdn, rtype, cleaned
