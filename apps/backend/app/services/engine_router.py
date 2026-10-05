from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services import engine_runtime


@dataclass(frozen=True)
class EngineExecution:
    operation: str
    engine: str
    value: Any


BinaryHandler = Callable[[bytes], tuple[Any, str]]


_BINARY_OPERATIONS: dict[str, BinaryHandler] = {
    "mail.byte_stats": engine_runtime.byte_stats,
    "mail.mime_scan": engine_runtime.mime_scan,
    "mail.sha256": engine_runtime.sha256_digest,
    "native.fingerprint": engine_runtime.fast_fingerprint,
    "native.blob_profile": engine_runtime.blob_profile,
}


PREFERRED_ENGINES: dict[str, str] = {
    "mail.byte_stats": "rust",
    "mail.mime_scan": "rust",
    "mail.sha256": "rust",
    "native.fingerprint": "cpp",
    "native.blob_profile": "cpp",
    "network.concurrent": "go",
    "enterprise.xml": "java",
}


def preferred_engine(operation: str) -> str:
    return PREFERRED_ENGINES.get(operation, "python")


def execute_binary(operation: str, data: bytes) -> EngineExecution:
    """Route bounded byte-oriented work while Python remains authoritative.

    Each native handler owns its fallback semantics. A specialist failure must
    therefore degrade to Python rather than fail a mailbox request.
    """
    handler = _BINARY_OPERATIONS.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported binary engine operation: {operation}")
    value, engine = handler(data)
    return EngineExecution(operation=operation, engine=engine, value=value)


def routing_status() -> dict[str, dict[str, str]]:
    return {
        operation: {
            "preferred": engine,
            "fallback": "python",
        }
        for operation, engine in PREFERRED_ENGINES.items()
    }


def execute_network(targets: list[dict], concurrency: int = 16) -> EngineExecution:
    """Route bounded concurrent network probes to Go with Python fallback."""
    value, engine = engine_runtime.network_probe(targets, concurrency)
    return EngineExecution(operation="network.concurrent", engine=engine, value=value)


def execute_enterprise_xml(xml_bytes: bytes) -> EngineExecution:
    """Route standards-heavy XML inspection to Java with Python fallback."""
    value, engine = engine_runtime.enterprise_xml_inspect(xml_bytes)
    return EngineExecution(operation="enterprise.xml", engine=engine, value=value)
