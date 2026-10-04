from __future__ import annotations

import ctypes
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx


RUST_LIBRARY = Path(os.getenv("ITHUTE_RUST_CORE_LIBRARY", "/opt/ithute-engines/libithute_rust_core.so"))
CPP_LIBRARY = Path(os.getenv("ITHUTE_CPP_NATIVE_LIBRARY", "/opt/ithute-engines/libithute_cpp_native.so"))
GO_WORKER_URL = os.getenv("ITHUTE_GO_WORKER_URL", "http://ithute-go-worker:8080").rstrip("/")
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


_rust: ctypes.CDLL | None = None
_cpp: ctypes.CDLL | None = None


def _load_rust() -> ctypes.CDLL | None:
    global _rust
    if _rust is not None:
        return _rust
    if not RUST_LIBRARY.is_file():
        return None
    library = ctypes.CDLL(str(RUST_LIBRARY))
    library.ithute_rust_byte_stats.argtypes = [
        ctypes.POINTER(ctypes.c_ubyte),
        ctypes.c_size_t,
        ctypes.POINTER(_RustByteStats),
    ]
    library.ithute_rust_byte_stats.restype = ctypes.c_int
    _rust = library
    return library


def _load_cpp() -> ctypes.CDLL | None:
    global _cpp
    if _cpp is not None:
        return _cpp
    if not CPP_LIBRARY.is_file():
        return None
    library = ctypes.CDLL(str(CPP_LIBRARY))
    library.ithute_cpp_fnv1a64.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t]
    library.ithute_cpp_fnv1a64.restype = ctypes.c_uint64
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


def engine_status() -> dict:
    rust_available = _load_rust() is not None
    cpp_available = _load_cpp() is not None
    go = go_worker_status()
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
                "capabilities": ["byte-stats"] if rust_available else [],
                "fallback": "python",
            },
            "go": go,
            "cpp": {
                "available": cpp_available,
                "mode": "native",
                "library": str(CPP_LIBRARY),
                "capabilities": ["fnv1a64"] if cpp_available else [],
                "fallback": "python",
            },
        },
    }


def sample_native_result(data: bytes) -> dict:
    stats, stats_engine = byte_stats(data)
    fingerprint, fingerprint_engine = fast_fingerprint(data)
    return {
        "stats": asdict(stats),
        "stats_engine": stats_engine,
        "fingerprint": str(fingerprint),
        "fingerprint_engine": fingerprint_engine,
    }
