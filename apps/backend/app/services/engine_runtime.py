from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import dns.exception
import dns.resolver
import dns.reversename
import httpx


RUST_LIBRARY = Path(os.getenv("ITHUTE_RUST_CORE_LIBRARY", "/opt/ithute-engines/libithute_rust_core.so"))
CPP_LIBRARY = Path(os.getenv("ITHUTE_CPP_NATIVE_LIBRARY", "/opt/ithute-engines/libithute_cpp_native.so"))
GO_WORKER_URL = os.getenv("ITHUTE_GO_WORKER_URL", "http://ithute-go-worker:8080").rstrip("/")
JAVA_WORKER_URL = os.getenv("ITHUTE_JAVA_WORKER_URL", "http://ithute-java-worker:8080").rstrip("/")
ENGINE_HTTP_TIMEOUT_SECONDS = float(os.getenv("ITHUTE_ENGINE_HTTP_TIMEOUT_SECONDS", "1.5"))


@dataclass(frozen=True)
class ByteStats:
    bytes: int
    lines: int
    ascii: int
    non_ascii: int


class _RustByteStats(ctypes.Structure):
    _fields_ = [
        ("bytes", ctypes.c_size_t),
        ("lines", ctypes.c_size_t),
        ("ascii", ctypes.c_size_t),
        ("non_ascii", ctypes.c_size_t),
    ]


@dataclass(frozen=True)
class MimeScan:
    bytes: int
    header_bytes: int
    body_bytes: int
    lines: int
    crlf_lines: int
    non_ascii: int
    nul_bytes: int
    boundary_markers: int
    attachment_signals: int


class _RustMimeScan(ctypes.Structure):
    _fields_ = [
        ("bytes", ctypes.c_size_t),
        ("header_bytes", ctypes.c_size_t),
        ("body_bytes", ctypes.c_size_t),
        ("lines", ctypes.c_size_t),
        ("crlf_lines", ctypes.c_size_t),
        ("non_ascii", ctypes.c_size_t),
        ("nul_bytes", ctypes.c_size_t),
        ("boundary_markers", ctypes.c_size_t),
        ("attachment_signals", ctypes.c_size_t),
    ]


@dataclass(frozen=True)
class BlobProfile:
    bytes: int
    nul_bytes: int
    control_bytes: int
    high_bytes: int
    fnv1a64: int


@dataclass(frozen=True)
class PushEnvelopeScan:
    bytes: int
    utf8_valid: bool
    json_object_shape: bool
    nul_bytes: int
    control_bytes: int


class _RustPushEnvelopeScan(ctypes.Structure):
    _fields_ = [
        ("bytes", ctypes.c_size_t),
        ("utf8_valid", ctypes.c_uint8),
        ("json_object_shape", ctypes.c_uint8),
        ("nul_bytes", ctypes.c_size_t),
        ("control_bytes", ctypes.c_size_t),
    ]


class _CppBlobProfile(ctypes.Structure):
    _fields_ = [
        ("bytes", ctypes.c_size_t),
        ("nul_bytes", ctypes.c_size_t),
        ("control_bytes", ctypes.c_size_t),
        ("high_bytes", ctypes.c_size_t),
        ("fnv1a64", ctypes.c_uint64),
    ]


_rust: ctypes.CDLL | None = None
_cpp: ctypes.CDLL | None = None


def _load_rust() -> ctypes.CDLL | None:
    global _rust
    if _rust is not None:
        return _rust
    if not RUST_LIBRARY.is_file():
        return None
    try:
        library = ctypes.CDLL(str(RUST_LIBRARY))
        library.ithute_rust_byte_stats.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(_RustByteStats),
        ]
        library.ithute_rust_byte_stats.restype = ctypes.c_int
        library.ithute_rust_mime_scan.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(_RustMimeScan),
        ]
        library.ithute_rust_mime_scan.restype = ctypes.c_int
        library.ithute_rust_sha256.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        library.ithute_rust_sha256.restype = ctypes.c_int
        library.ithute_rust_hmac_sha256.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        library.ithute_rust_hmac_sha256.restype = ctypes.c_int
    except (OSError, AttributeError):
        return None
    _rust = library
    return library


def _load_cpp() -> ctypes.CDLL | None:
    global _cpp
    if _cpp is not None:
        return _cpp
    if not CPP_LIBRARY.is_file():
        return None
    try:
        library = ctypes.CDLL(str(CPP_LIBRARY))
        library.ithute_cpp_fnv1a64.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t]
        library.ithute_cpp_fnv1a64.restype = ctypes.c_uint64
        library.ithute_cpp_blob_profile_scan.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(_CppBlobProfile),
        ]
        library.ithute_cpp_blob_profile_scan.restype = ctypes.c_int
    except (OSError, AttributeError):
        return None
    _cpp = library
    return library


def python_byte_stats(data: bytes) -> ByteStats:
    return ByteStats(
        bytes=len(data),
        lines=0 if not data else data.count(b"\n") + 1,
        ascii=sum(1 for value in data if value < 128),
        non_ascii=sum(1 for value in data if value >= 128),
    )


def byte_stats(data: bytes) -> tuple[ByteStats, str]:
    """Use Rust when installed and fall back to Python without changing callers."""
    library = _load_rust()
    if library is None:
        return python_byte_stats(data), "python-fallback"

    output = _RustByteStats()
    if data:
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    else:
        pointer = ctypes.POINTER(ctypes.c_ubyte)()
    code = library.ithute_rust_byte_stats(pointer, len(data), ctypes.byref(output))
    if code != 0:
        return python_byte_stats(data), "python-fallback"
    return ByteStats(output.bytes, output.lines, output.ascii, output.non_ascii), "rust"


def python_mime_scan(data: bytes) -> MimeScan:
    split_at = data.find(b"\r\n\r\n")
    separator = 4
    if split_at < 0:
        split_at = data.find(b"\n\n")
        separator = 2
    header_bytes = len(data) if split_at < 0 else split_at + separator
    lower = data.lower()
    attachment_signals = int(
        b"content-disposition" in lower or b"filename" in lower or b"name" in lower
    )
    return MimeScan(
        bytes=len(data),
        header_bytes=header_bytes,
        body_bytes=max(0, len(data) - header_bytes),
        lines=0 if not data else data.count(b"\n") + 1,
        crlf_lines=data.count(b"\r\n"),
        non_ascii=sum(1 for value in data if value >= 128),
        nul_bytes=data.count(b"\x00"),
        boundary_markers=sum(
            1 for line in data.split(b"\n")
            if line.lstrip(b"\r").startswith(b"--")
        ),
        attachment_signals=attachment_signals,
    )


def mime_scan(data: bytes) -> tuple[MimeScan, str]:
    """Use Rust for the raw RFC822/MIME pre-scan with a Python reference fallback."""
    library = _load_rust()
    if library is None:
        return python_mime_scan(data), "python-fallback"

    output = _RustMimeScan()
    if data:
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    else:
        pointer = ctypes.POINTER(ctypes.c_ubyte)()
    try:
        code = library.ithute_rust_mime_scan(pointer, len(data), ctypes.byref(output))
    except (OSError, ValueError, ctypes.ArgumentError):
        return python_mime_scan(data), "python-fallback"
    if code != 0:
        return python_mime_scan(data), "python-fallback"
    return MimeScan(
        output.bytes,
        output.header_bytes,
        output.body_bytes,
        output.lines,
        output.crlf_lines,
        output.non_ascii,
        output.nul_bytes,
        output.boundary_markers,
        output.attachment_signals,
    ), "rust"


def python_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_digest(data: bytes) -> tuple[str, str]:
    """Hash mail/attachment bytes in Rust with an exact hashlib fallback."""
    library = _load_rust()
    if library is None:
        return python_sha256(data), "python-fallback"

    if data:
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    else:
        pointer = ctypes.POINTER(ctypes.c_ubyte)()

    output = (ctypes.c_ubyte * 32)()
    try:
        code = library.ithute_rust_sha256(pointer, len(data), output)
    except (OSError, ValueError, ctypes.ArgumentError):
        return python_sha256(data), "python-fallback"
    if code != 0:
        return python_sha256(data), "python-fallback"
    return bytes(output).hex(), "rust"


def python_hmac_sha256(key: bytes, data: bytes) -> str:
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def hmac_sha256(key: bytes, data: bytes) -> tuple[str, str]:
    """Compute HMAC-SHA256 in Rust with an exact stdlib fallback."""
    library = _load_rust()
    if library is None:
        return python_hmac_sha256(key, data), "python-fallback"

    if key:
        key_buffer = (ctypes.c_ubyte * len(key)).from_buffer_copy(key)
        key_pointer = ctypes.cast(key_buffer, ctypes.POINTER(ctypes.c_ubyte))
    else:
        key_pointer = ctypes.POINTER(ctypes.c_ubyte)()
    if data:
        data_buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        data_pointer = ctypes.cast(data_buffer, ctypes.POINTER(ctypes.c_ubyte))
    else:
        data_pointer = ctypes.POINTER(ctypes.c_ubyte)()

    output = (ctypes.c_ubyte * 32)()
    try:
        code = library.ithute_rust_hmac_sha256(
            key_pointer,
            len(key),
            data_pointer,
            len(data),
            output,
        )
    except (OSError, ValueError, ctypes.ArgumentError):
        return python_hmac_sha256(key, data), "python-fallback"
    if code != 0:
        return python_hmac_sha256(key, data), "python-fallback"
    return bytes(output).hex(), "rust"


def _python_fnv1a64(data: bytes) -> int:
    value = 14695981039346656037
    for byte in data:
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def fast_fingerprint(data: bytes) -> tuple[int, str]:
    """C++ is a narrow optional turbo path; Python remains the safe fallback."""
    library = _load_cpp()
    if library is None:
        return _python_fnv1a64(data), "python-fallback"
    if data:
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    else:
        pointer = ctypes.POINTER(ctypes.c_ubyte)()
    return int(library.ithute_cpp_fnv1a64(pointer, len(data))), "cpp"



def python_blob_profile(data: bytes) -> BlobProfile:
    return BlobProfile(
        bytes=len(data),
        nul_bytes=data.count(b"\x00"),
        control_bytes=sum(1 for value in data if value < 32 and value not in {9, 10, 13}),
        high_bytes=sum(1 for value in data if value >= 128),
        fnv1a64=_python_fnv1a64(data),
    )


def blob_profile(data: bytes) -> tuple[BlobProfile, str]:
    """Profile binary payloads in one C++ pass with an exact Python fallback."""
    library = _load_cpp()
    if library is None:
        return python_blob_profile(data), "python-fallback"
    if data:
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    else:
        pointer = ctypes.POINTER(ctypes.c_ubyte)()
    output = _CppBlobProfile()
    try:
        code = library.ithute_cpp_blob_profile_scan(pointer, len(data), ctypes.byref(output))
    except (OSError, ValueError, ctypes.ArgumentError):
        return python_blob_profile(data), "python-fallback"
    if code != 0:
        return python_blob_profile(data), "python-fallback"
    return BlobProfile(
        bytes=output.bytes,
        nul_bytes=output.nul_bytes,
        control_bytes=output.control_bytes,
        high_bytes=output.high_bytes,
        fnv1a64=int(output.fnv1a64),
    ), "cpp"

def go_worker_status() -> dict:
    try:
        with httpx.Client(timeout=ENGINE_HTTP_TIMEOUT_SECONDS, trust_env=False) as client:
            response = client.get(f"{GO_WORKER_URL}/v1/capabilities")
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or body.get("engine") != "go":
            raise ValueError("invalid Go worker capability response")
        return {"available": True, **body}
    except (httpx.HTTPError, ValueError, TypeError):
        return {
            "available": False,
            "service": "ithute-go-worker",
            "engine": "go",
            "version": None,
            "capabilities": [],
        }



def _python_tcp_probe(target: dict) -> dict:
    host = str(target["host"]).strip()
    port = int(target["port"])
    timeout_ms = int(target.get("timeout_ms") or 1200)
    started = time.perf_counter()
    reachable = False
    error = ""
    try:
        with socket.create_connection((host, port), timeout=timeout_ms / 1000):
            reachable = True
    except OSError:
        error = "unreachable"
    latency_ms = (time.perf_counter() - started) * 1000
    return {
        "id": str(target["id"]),
        "host": host,
        "port": port,
        "reachable": reachable,
        "latency_ms": round(latency_ms, 3),
        **({"error": error} if error else {}),
    }


def python_network_probe(targets: list[dict], concurrency: int = 16) -> dict:
    workers = max(1, min(int(concurrency or 16), 32))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_python_tcp_probe, targets))
    return {"engine": "python-fallback", "checked": len(results), "results": results}


def network_probe(targets: list[dict], concurrency: int = 16) -> tuple[dict, str]:
    """Use Go for bounded concurrent TCP reachability checks with Python fallback."""
    if not targets:
        return {"engine": "python-fallback", "checked": 0, "results": []}, "python-fallback"

    payload = {"targets": targets[:64], "concurrency": max(1, min(int(concurrency or 16), 32))}
    try:
        with httpx.Client(timeout=max(ENGINE_HTTP_TIMEOUT_SECONDS, 6.0), trust_env=False) as client:
            response = client.post(f"{GO_WORKER_URL}/v1/network/probe", json=payload)
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or body.get("engine") != "go":
            raise ValueError("invalid Go network probe response")
        results = body.get("results")
        if not isinstance(results, list) or int(body.get("checked") or -1) != len(results):
            raise ValueError("invalid Go network probe result set")
        return body, "go"
    except (httpx.HTTPError, ValueError, TypeError):
        body = python_network_probe(payload["targets"], payload["concurrency"])
        return body, "python-fallback"


def _python_dns_query(query: dict) -> dict:
    query_id = str(query.get("id") or "")
    name = str(query.get("name") or "").strip()
    rtype = str(query.get("type") or "").strip().upper()
    values: list[str] = []
    error = ""
    try:
        if rtype == "PTR":
            reverse_name = dns.reversename.from_address(name)
            answers = dns.resolver.resolve(reverse_name, "PTR", lifetime=5)
            values = [str(answer.target).rstrip(".").lower() for answer in answers]
        else:
            answers = dns.resolver.resolve(name, rtype, lifetime=5)
            if rtype == "CNAME":
                values = [str(answer.target).rstrip(".").lower() for answer in answers]
            elif rtype == "MX":
                values = [
                    f"{int(answer.preference)} {str(answer.exchange).rstrip('.').lower()}"
                    for answer in answers
                ]
            elif rtype == "NS":
                values = [str(answer.target).rstrip(".").lower() for answer in answers]
            elif rtype == "TXT":
                rows: list[str] = []
                for answer in answers:
                    parts = getattr(answer, "strings", None)
                    if parts is not None:
                        rows.append("".join(part.decode() if isinstance(part, bytes) else str(part) for part in parts))
                    else:
                        rows.append(str(answer).strip().strip('"'))
                values = rows
            else:
                values = [str(answer).strip().rstrip(".").lower() for answer in answers]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        error = "not_found"
    except (dns.resolver.NoNameservers, dns.exception.Timeout, OSError, ValueError):
        error = "lookup_failed"
    return {
        "id": query_id,
        "name": name,
        "type": rtype,
        "values": values,
        **({"error": error} if error else {}),
    }


def python_dns_lookup(queries: list[dict], concurrency: int = 16) -> dict:
    bounded = queries[:64]
    workers = max(1, min(int(concurrency or 16), 32))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_python_dns_query, bounded))
    return {"engine": "python-fallback", "checked": len(results), "results": results}


def dns_lookup(queries: list[dict], concurrency: int = 16) -> tuple[dict, str]:
    """Resolve bounded DNS batches in Go with dnspython as the compatibility fallback."""
    if not queries:
        return {"engine": "python-fallback", "checked": 0, "results": []}, "python-fallback"
    payload = {
        "queries": queries[:64],
        "concurrency": max(1, min(int(concurrency or 16), 32)),
    }
    try:
        with httpx.Client(timeout=max(ENGINE_HTTP_TIMEOUT_SECONDS, 6.0), trust_env=False) as client:
            response = client.post(f"{GO_WORKER_URL}/v1/dns/lookup", json=payload)
            response.raise_for_status()
            body = response.json()
        results = body.get("results") if isinstance(body, dict) else None
        if body.get("engine") != "go" or not isinstance(results, list):
            raise ValueError("invalid Go DNS response")
        if int(body.get("checked") or -1) != len(results):
            raise ValueError("invalid Go DNS result count")
        return body, "go"
    except (httpx.HTTPError, ValueError, TypeError):
        return python_dns_lookup(payload["queries"], payload["concurrency"]), "python-fallback"


def go_origin_probe(payload: dict) -> tuple[dict | None, str]:
    """Run the already policy-vetted public origin probe in Go.

    The caller remains responsible for URL parsing and SSRF/public-address policy.
    Returning None means the caller should execute its established Python fallback.
    """
    try:
        with httpx.Client(timeout=max(ENGINE_HTTP_TIMEOUT_SECONDS, 35.0), trust_env=False) as client:
            response = client.post(f"{GO_WORKER_URL}/v1/network/origin", json=payload)
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or body.get("engine") != "go":
            raise ValueError("invalid Go origin probe response")
        required = {"healthy", "resolved_ip", "status_code", "latency_ms", "error"}
        if any(key not in body for key in required):
            raise ValueError("invalid Go origin probe shape")
        return body, "go"
    except (httpx.HTTPError, ValueError, TypeError):
        return None, "python-fallback"


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def python_enterprise_xml_inspect(xml_bytes: bytes) -> dict:
    """Reference XML structural inspection used when the Java worker is unavailable."""
    if len(xml_bytes) > 10 * 1024 * 1024:
        raise ValueError("enterprise XML exceeds the maximum size")
    upper = xml_bytes.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("enterprise XML DTD/entities are not allowed")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("enterprise XML is invalid") from exc

    element_count = 0
    attribute_count = 0
    text_characters = 0
    max_depth = 0
    counts: dict[str, int] = {}
    stack: list[tuple[ET.Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        element_count += 1
        if element_count > 100_000:
            raise ValueError("enterprise XML has too many elements")
        if depth > 128:
            raise ValueError("enterprise XML nesting is too deep")
        max_depth = max(max_depth, depth)
        attribute_count += len(element.attrib)
        name = _xml_local_name(str(element.tag))
        counts[name] = counts.get(name, 0) + 1
        if element.text:
            text_characters += len(element.text.strip())
        for child in reversed(list(element)):
            if child.tail:
                text_characters += len(child.tail.strip())
            stack.append((child, depth + 1))

    root_tag = str(root.tag)
    namespace = ""
    if root_tag.startswith("{") and "}" in root_tag:
        namespace = root_tag[1:].split("}", 1)[0]
    top_elements = [
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]
    ]
    return {
        "engine": "python-fallback",
        "parser_version": "1",
        "root": _xml_local_name(root_tag),
        "namespace": namespace,
        "element_count": element_count,
        "attribute_count": attribute_count,
        "text_characters": text_characters,
        "max_depth": max_depth,
        "top_elements": top_elements,
    }


def enterprise_xml_inspect(xml_bytes: bytes) -> tuple[dict, str]:
    """Use Java for secure enterprise XML inspection with a Python reference fallback."""
    if len(xml_bytes) > 10 * 1024 * 1024:
        raise ValueError("enterprise XML exceeds the maximum size")
    try:
        with httpx.Client(timeout=max(ENGINE_HTTP_TIMEOUT_SECONDS, 6.0), trust_env=False) as client:
            response = client.post(
                f"{JAVA_WORKER_URL}/v1/xml/inspect",
                content=xml_bytes,
                headers={"Content-Type": "application/xml"},
            )
            response.raise_for_status()
            body = response.json()
        required = (
            "root",
            "namespace",
            "element_count",
            "attribute_count",
            "text_characters",
            "max_depth",
            "top_elements",
        )
        if not isinstance(body, dict) or body.get("engine") != "java":
            raise ValueError("invalid Java XML response")
        if any(key not in body for key in required) or not isinstance(body.get("top_elements"), list):
            raise ValueError("invalid Java XML inspection shape")
        return body, "java"
    except (httpx.HTTPError, ValueError, TypeError):
        return python_enterprise_xml_inspect(xml_bytes), "python-fallback"


def java_worker_status() -> dict:
    try:
        with httpx.Client(timeout=ENGINE_HTTP_TIMEOUT_SECONDS, trust_env=False) as client:
            response = client.get(f"{JAVA_WORKER_URL}/v1/capabilities")
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or body.get("engine") != "java":
            raise ValueError("invalid Java worker capability response")
        return {"available": True, **body}
    except (httpx.HTTPError, ValueError, TypeError):
        return {
            "available": False,
            "service": "ithute-java-worker",
            "engine": "java",
            "version": None,
            "capabilities": [],
        }


def engine_status() -> dict:
    rust_available = _load_rust() is not None
    cpp_available = _load_cpp() is not None
    go = go_worker_status()
    java = java_worker_status()
    return {
        "brain": {
            "engine": "python",
            "authoritative": True,
            "responsibilities": [
                "authorization",
                "tenancy",
                "billing",
                "business-rules",
                "database-orchestration",
                "api-control",
            ],
        },
        "engines": {
            "rust": {
                "available": rust_available,
                "mode": "native",
                "library": str(RUST_LIBRARY),
                "capabilities": ["byte-stats", "mime-prescan", "sha256", "hmac-sha256"] if rust_available else [],
                "fallback": "python",
            },
            "go": go,
            "java": java,
            "cpp": {
                "available": cpp_available,
                "mode": "native",
                "library": str(CPP_LIBRARY),
                "capabilities": ["fnv1a64", "blob-profile"] if cpp_available else [],
                "fallback": "python",
            },
        },
    }


def sample_native_result(data: bytes) -> dict:
    stats, stats_engine = byte_stats(data)
    mime, mime_engine = mime_scan(data)
    fingerprint, fingerprint_engine = fast_fingerprint(data)
    sha256, sha256_engine = sha256_digest(data)
    return {
        "stats": asdict(stats),
        "stats_engine": stats_engine,
        "mime": asdict(mime),
        "mime_engine": mime_engine,
        "fingerprint": str(fingerprint),
        "fingerprint_engine": fingerprint_engine,
        "sha256": sha256,
        "sha256_engine": sha256_engine,
    }
