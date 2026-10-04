from __future__ import annotations

import gzip
import hashlib
import io
import zipfile
from datetime import datetime, timezone
from ipaddress import ip_address
from xml.etree import ElementTree as ET

import httpx

from app.services.engine_runtime import ENGINE_HTTP_TIMEOUT_SECONDS, JAVA_WORKER_URL

MAX_DMARC_COMPRESSED_BYTES = 10 * 1024 * 1024
MAX_DMARC_XML_BYTES = 10 * 1024 * 1024
MAX_DMARC_RECORDS = 100_000


class DmarcReportError(ValueError):
    pass


def _bounded_read(stream, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        part = stream.read(65536)
        if not part:
            break
        total += len(part)
        if total > limit:
            raise DmarcReportError("DMARC report exceeds the maximum uncompressed size")
        chunks.append(part)
    return b"".join(chunks)


def extract_dmarc_xml(data: bytes, filename: str = "") -> bytes:
    if len(data) > MAX_DMARC_COMPRESSED_BYTES:
        raise DmarcReportError("DMARC report exceeds the maximum upload size")
    lower = (filename or "").strip().lower()

    try:
        if lower.endswith(".gz") or data[:2] == b"\x1f\x8b":
            return _bounded_read(gzip.GzipFile(fileobj=io.BytesIO(data)), MAX_DMARC_XML_BYTES)

        if lower.endswith(".zip") or data[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = [
                    item for item in archive.infolist()
                    if not item.is_dir() and not item.filename.startswith("__MACOSX/")
                ]
                if len(entries) != 1:
                    raise DmarcReportError("DMARC ZIP report must contain exactly one file")
                item = entries[0]
                if item.file_size > MAX_DMARC_XML_BYTES:
                    raise DmarcReportError("DMARC XML inside ZIP exceeds the maximum size")
                with archive.open(item, "r") as stream:
                    return _bounded_read(stream, MAX_DMARC_XML_BYTES)
    except (OSError, EOFError, zipfile.BadZipFile) as exc:
        raise DmarcReportError("DMARC report archive is invalid") from exc

    if len(data) > MAX_DMARC_XML_BYTES:
        raise DmarcReportError("DMARC XML exceeds the maximum size")
    return data


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    for node in list(element):
        if node.tag.rsplit("}", 1)[-1] == name:
            return node
    return None


def _text(element: ET.Element | None, *path: str) -> str:
    current = element
    for part in path:
        current = _child(current, part)
        if current is None:
            return ""
    return (current.text or "").strip()


def _int(value: str, fallback: int = 0) -> int:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return fallback


def _float_rate(passed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((passed * 100.0) / total, 2)


def python_parse_dmarc_xml(xml_bytes: bytes) -> dict:
    if len(xml_bytes) > MAX_DMARC_XML_BYTES:
        raise DmarcReportError("DMARC XML exceeds the maximum size")
    upper = xml_bytes[:262144].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise DmarcReportError("DMARC XML DTD/entities are not allowed")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise DmarcReportError("DMARC XML is invalid") from exc

    if root.tag.rsplit("}", 1)[-1] != "feedback":
        raise DmarcReportError("DMARC XML root must be feedback")

    metadata = {
        "org_name": _text(root, "report_metadata", "org_name")[:255],
        "email": _text(root, "report_metadata", "email")[:320],
        "report_id": _text(root, "report_metadata", "report_id")[:512],
        "begin": max(0, _int(_text(root, "report_metadata", "date_range", "begin"))),
        "end": max(0, _int(_text(root, "report_metadata", "date_range", "end"))),
    }
    policy = {
        "domain": _text(root, "policy_published", "domain").lower().rstrip(".")[:253],
        "adkim": _text(root, "policy_published", "adkim").lower()[:16],
        "aspf": _text(root, "policy_published", "aspf").lower()[:16],
        "p": _text(root, "policy_published", "p").lower()[:32],
        "sp": _text(root, "policy_published", "sp").lower()[:32],
        "pct": min(100, max(0, _int(_text(root, "policy_published", "pct"), 100))),
    }

    records: list[dict] = []
    total = passed = failed = 0
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "record":
            continue
        if len(records) >= MAX_DMARC_RECORDS:
            raise DmarcReportError("DMARC report contains too many records")
        count = max(0, _int(_text(element, "row", "count")))
        dkim = _text(element, "row", "policy_evaluated", "dkim").lower()[:32]
        spf = _text(element, "row", "policy_evaluated", "spf").lower()[:32]
        aligned = dkim == "pass" or spf == "pass"
        source_ip = _text(element, "row", "source_ip")[:64]
        try:
            source_ip = str(ip_address(source_ip))
        except ValueError:
            source_ip = source_ip
        row = {
            "source_ip": source_ip,
            "count": count,
            "disposition": _text(element, "row", "policy_evaluated", "disposition").lower()[:32],
            "dkim": dkim,
            "spf": spf,
            "header_from": _text(element, "identifiers", "header_from").lower().rstrip(".")[:253],
            "envelope_from": _text(element, "identifiers", "envelope_from").lower().rstrip(".")[:253],
            "dmarc_pass": aligned,
        }
        records.append(row)
        total += count
        if aligned:
            passed += count
        else:
            failed += count

    return {
        "engine": "python-fallback",
        "parser_version": "1",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "policy": policy,
        "summary": {
            "total_messages": total,
            "passed_messages": passed,
            "failed_messages": failed,
            "pass_rate_percent": _float_rate(passed, total),
        },
        "records": records,
    }


def _valid_result_shape(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return all(isinstance(value.get(key), dict) for key in ("metadata", "policy", "summary")) and isinstance(value.get("records"), list)


def parse_dmarc_xml(xml_bytes: bytes) -> tuple[dict, str]:
    try:
        with httpx.Client(
            timeout=max(ENGINE_HTTP_TIMEOUT_SECONDS, 5.0),
            trust_env=False,
        ) as client:
            response = client.post(
                f"{JAVA_WORKER_URL}/v1/dmarc/parse",
                content=xml_bytes,
                headers={"Content-Type": "application/xml"},
            )
            response.raise_for_status()
            body = response.json()
        if not _valid_result_shape(body) or body.get("engine") != "java":
            raise ValueError("invalid Java DMARC response")
        if len(body.get("records") or []) > MAX_DMARC_RECORDS:
            raise ValueError("Java DMARC response exceeds record limit")
        return body, "java"
    except (httpx.HTTPError, ValueError, TypeError):
        return python_parse_dmarc_xml(xml_bytes), "python-fallback"


def normalized_report(result: dict, expected_domain: str) -> dict:
    metadata = dict(result.get("metadata") or {})
    policy = dict(result.get("policy") or {})
    summary = dict(result.get("summary") or {})
    records = list(result.get("records") or [])

    policy_domain = str(policy.get("domain") or "").lower().rstrip(".")
    expected = expected_domain.lower().rstrip(".")
    if policy_domain != expected:
        raise DmarcReportError(
            f"DMARC report policy domain '{policy_domain or 'missing'}' does not match '{expected}'"
        )

    report_id = str(metadata.get("report_id") or "").strip()[:512]
    reporter_org = str(metadata.get("org_name") or "").strip()[:255]
    if not report_id or not reporter_org:
        raise DmarcReportError("DMARC report metadata must include org_name and report_id")

    clean_records: list[dict] = []
    total = passed = failed = 0
    for item in records[:MAX_DMARC_RECORDS]:
        if not isinstance(item, dict):
            continue
        count = max(0, _int(str(item.get("count") or "0")))
        dmarc_pass = bool(item.get("dmarc_pass"))
        source_ip = str(item.get("source_ip") or "")[:64]
        try:
            source_ip = str(ip_address(source_ip))
        except ValueError:
            pass
        clean = {
            "source_ip": source_ip,
            "count": count,
            "disposition": str(item.get("disposition") or "")[:32].lower(),
            "dkim": str(item.get("dkim") or "")[:32].lower(),
            "spf": str(item.get("spf") or "")[:32].lower(),
            "header_from": str(item.get("header_from") or "")[:253].lower().rstrip("."),
            "envelope_from": str(item.get("envelope_from") or "")[:253].lower().rstrip("."),
            "dmarc_pass": dmarc_pass,
        }
        clean_records.append(clean)
        total += count
        if dmarc_pass:
            passed += count
        else:
            failed += count

    return {
        "engine": "java" if result.get("engine") == "java" else "python-fallback",
        "parser_version": str(result.get("parser_version") or "1")[:32],
        "metadata": {
            "org_name": reporter_org,
            "email": str(metadata.get("email") or "")[:320],
            "report_id": report_id,
            "begin": max(0, _int(str(metadata.get("begin") or "0"))),
            "end": max(0, _int(str(metadata.get("end") or "0"))),
        },
        "policy": {
            "domain": policy_domain,
            "adkim": str(policy.get("adkim") or "")[:16].lower(),
            "aspf": str(policy.get("aspf") or "")[:16].lower(),
            "p": str(policy.get("p") or "")[:32].lower(),
            "sp": str(policy.get("sp") or "")[:32].lower(),
            "pct": min(100, max(0, _int(str(policy.get("pct") or "100"), 100))),
        },
        "summary": {
            "total_messages": total,
            "passed_messages": passed,
            "failed_messages": failed,
            "pass_rate_percent": _float_rate(passed, total),
        },
        "records": clean_records,
    }


def report_sha256(xml_bytes: bytes) -> str:
    return hashlib.sha256(xml_bytes).hexdigest()


def epoch_datetime(value: int) -> datetime | None:
    if value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
