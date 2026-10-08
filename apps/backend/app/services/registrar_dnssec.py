from __future__ import annotations

from dataclasses import dataclass
import hashlib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from app.core.config import settings


class RegistrarError(RuntimeError):
    pass


# OpenSRS currently documents these DNSSEC algorithms for set_dnssec_info.
# Fail closed rather than submitting an algorithm the registrar may reject.
OPENSRS_DNSSEC_ALGORITHMS = {5, 6, 7, 8, 10, 253, 254}
OPENSRS_DIGEST_TYPES = {1, 2, 3, 4}


@dataclass(frozen=True)
class DSRecord:
    key_tag: int
    algorithm: int
    digest_type: int
    digest: str

    @classmethod
    def parse(cls, value: str) -> "DSRecord":
        parts = value.strip().split()
        if len(parts) != 4:
            raise ValueError("DS record must contain key tag, algorithm, digest type and digest")
        key_tag, algorithm, digest_type = (int(parts[i]) for i in range(3))
        digest = parts[3].strip().upper()
        if not 0 <= key_tag <= 65535:
            raise ValueError("DS key tag is out of range")
        if not 1 <= algorithm <= 255 or not 1 <= digest_type <= 255:
            raise ValueError("DS algorithm or digest type is out of range")
        if not digest or any(ch not in "0123456789ABCDEF" for ch in digest):
            raise ValueError("DS digest must be hexadecimal")
        return cls(key_tag, algorithm, digest_type, digest)

    def as_opensrs(self) -> dict:
        return {
            "key_tag": self.key_tag,
            "algorithm": self.algorithm,
            "digest_type": self.digest_type,
            "digest": self.digest,
        }

    def text(self) -> str:
        return f"{self.key_tag} {self.algorithm} {self.digest_type} {self.digest}"


def preferred_ds(values: list[str], *, allowed_algorithms: set[int] | None = None) -> DSRecord | None:
    records: list[DSRecord] = []
    for value in values:
        try:
            record = DSRecord.parse(value)
            if allowed_algorithms is None or record.algorithm in allowed_algorithms:
                records.append(record)
        except (TypeError, ValueError):
            continue
    if not records:
        return None
    rank = {2: 0, 4: 1, 1: 2}
    return sorted(records, key=lambda item: (rank.get(item.digest_type, 99), item.key_tag, item.algorithm))[0]


def _item_value(item: ET.Element):
    children = list(item)
    if not children:
        return (item.text or "").strip()
    child = children[0]
    if child.tag == "dt_assoc":
        return {entry.attrib.get("key", ""): _item_value(entry) for entry in child.findall("item")}
    if child.tag == "dt_array":
        return [_item_value(entry) for entry in child.findall("item")]
    return (child.text or "").strip()


def _parse_response(xml_text: str) -> dict:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RegistrarError("OpenSRS returned invalid XML") from exc
    assoc = root.find("./body/data_block/dt_assoc")
    if assoc is None:
        raise RegistrarError("OpenSRS response is missing data")
    data = {item.attrib.get("key", ""): _item_value(item) for item in assoc.findall("item")}
    success = str(data.get("is_success", "0")).lower() in {"1", "true"}
    if not success:
        raise RegistrarError(str(data.get("response_text") or "OpenSRS request failed"))
    return data


def _xml_item(parent: ET.Element, key: str, value):
    item = ET.SubElement(parent, "item", {"key": str(key)})
    if isinstance(value, dict):
        assoc = ET.SubElement(item, "dt_assoc")
        for child_key, child_value in value.items():
            _xml_item(assoc, child_key, child_value)
    elif isinstance(value, list):
        array = ET.SubElement(item, "dt_array")
        for index, child_value in enumerate(value):
            _xml_item(array, str(index), child_value)
    else:
        item.text = str(value)


def _build_request(action: str, attributes: dict) -> str:
    root = ET.Element("OPS_envelope")
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "version").text = "0.9"
    body = ET.SubElement(root, "body")
    block = ET.SubElement(body, "data_block")
    assoc = ET.SubElement(block, "dt_assoc")
    _xml_item(assoc, "protocol", "XCP")
    _xml_item(assoc, "action", action)
    _xml_item(assoc, "object", "DOMAIN")
    _xml_item(assoc, "attributes", attributes)
    return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n' + ET.tostring(root, encoding="unicode")


class OpenSRSRegistrar:
    """OpenSRS parent-DS client.

    OpenSRS forwards DS values to the registry. The production endpoint requires
    the Ithute server's public IP to be whitelisted in the OpenSRS reseller account.
    """

    def __init__(self) -> None:
        self.url = settings.opensrs_api_url.strip()
        self.username = (settings.opensrs_username or "").strip()
        self.api_key = (settings.opensrs_api_key or "").strip()
        self.timeout = settings.external_provider_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.url and self.username and self.api_key)

    def _request(self, action: str, attributes: dict) -> dict:
        if not self.configured:
            raise RegistrarError("OpenSRS registrar integration is not configured")
        xml = _build_request(action, attributes)
        first = hashlib.md5((xml + self.api_key).encode()).hexdigest()
        signature = hashlib.md5((first + self.api_key).encode()).hexdigest()
        request = Request(
            self.url,
            data=xml.encode(),
            method="POST",
            headers={
                "Content-Type": "text/xml",
                "X-Username": self.username,
                "X-Signature": signature,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode(errors="replace")
                if response.status != 200:
                    raise RegistrarError(f"OpenSRS returned HTTP {response.status}")
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise RegistrarError(f"OpenSRS HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RegistrarError(f"OpenSRS unavailable: {exc}") from exc
        return _parse_response(raw)

    def get_dnssec(self, domain: str) -> list[DSRecord]:
        data = self._request("get", {"domain": domain, "type": "dnssec"})
        attrs = data.get("attributes")
        raw = attrs.get("dnssec", []) if isinstance(attrs, dict) else []
        if isinstance(raw, dict):
            raw = list(raw.values())
        records: list[DSRecord] = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                records.append(
                    DSRecord(
                        int(item["key_tag"]),
                        int(item["algorithm"]),
                        int(item["digest_type"]),
                        str(item["digest"]).upper(),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return records

    def set_dnssec(self, domain: str, records: list[DSRecord]) -> None:
        unsupported = [record for record in records if record.algorithm not in OPENSRS_DNSSEC_ALGORITHMS or record.digest_type not in OPENSRS_DIGEST_TYPES]
        if unsupported:
            record = unsupported[0]
            raise RegistrarError(
                f"OpenSRS does not advertise support for DNSSEC algorithm {record.algorithm} "
                f"with digest type {record.digest_type}. Do not publish an incompatible DS record."
            )
        self._request("set_dnssec_info", {"domain": domain, "dnssec": [record.as_opensrs() for record in records]})

    def publish(self, domain: str, record: DSRecord) -> list[DSRecord]:
        current = self.get_dnssec(domain)
        if record not in current:
            current.append(record)
            self.set_dnssec(domain, current)
        return current

    def remove_managed(self, domain: str, managed: list[DSRecord]) -> list[DSRecord]:
        current = self.get_dnssec(domain)
        managed_set = set(managed)
        remaining = [record for record in current if record not in managed_set]
        if remaining != current:
            self.set_dnssec(domain, remaining)
        return remaining
