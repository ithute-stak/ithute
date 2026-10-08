"""Pure DNSSEC monitor transition rules.

The caller is responsible for storing state, scheduling checks and delivering
notifications. This module makes no network or database changes.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonitorState:
    code: str | None = None
    failures: int = 0
    status: str = "healthy"


def transition(previous: MonitorState, observation: dict, *, threshold: int = 3) -> tuple[MonitorState, list[str]]:
    if threshold < 1:
        raise ValueError("threshold must be positive")
    severity = observation.get("severity")
    code = observation.get("code")
    if severity == "healthy":
        events = ["recovered"] if previous.status == "open" else []
        return MonitorState(), events
    if severity == "unknown":
        # Never silently recover or open an incident based on inconclusive data.
        return previous, []
    if severity not in {"warning", "critical"} or not isinstance(code, str) or not code:
        raise ValueError("invalid observation")
    count = previous.failures + 1 if previous.code == code else 1
    if previous.status == "open" and previous.code == code:
        return MonitorState(code, count, "open"), []
    if count >= threshold:
        return MonitorState(code, count, "open"), ["opened"]
    return MonitorState(code, count, "pending"), []
