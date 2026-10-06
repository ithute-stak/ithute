from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


MIN_LABEL_CONFIDENCE = 0.80
MIN_BINARY_LABELS = 40
MIN_PER_CLASS = 12
MIN_DISTINCT_SERVERS = 3
MAX_CLASS_IMBALANCE_RATIO = 3.0

BINARY_POSITIVE = "confirmed_failure"
BINARY_NEGATIVE = "false_positive"


def _value(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def supervised_training_readiness(rows: Iterable[Any]) -> dict[str, Any]:
    all_rows = list(rows)
    high_confidence = [
        row
        for row in all_rows
        if float(_value(row, "confidence", 0.0) or 0.0) >= MIN_LABEL_CONFIDENCE
    ]
    binary = [
        row
        for row in high_confidence
        if str(_value(row, "label", "")) in {BINARY_POSITIVE, BINARY_NEGATIVE}
    ]

    labels = Counter(str(_value(row, "label", "")) for row in all_rows)
    high_conf_labels = Counter(str(_value(row, "label", "")) for row in high_confidence)
    positive = sum(1 for row in binary if str(_value(row, "label", "")) == BINARY_POSITIVE)
    negative = sum(1 for row in binary if str(_value(row, "label", "")) == BINARY_NEGATIVE)
    servers = {str(_value(row, "server_id", "")) for row in binary if _value(row, "server_id")}
    components = {
        str(_value(row, "component", "unknown") or "unknown")
        for row in binary
    }

    smaller = min(positive, negative)
    larger = max(positive, negative)
    imbalance_ratio = (larger / smaller) if smaller else None

    gates = {
        "total_binary_labels": len(binary) >= MIN_BINARY_LABELS,
        "positive_labels": positive >= MIN_PER_CLASS,
        "negative_labels": negative >= MIN_PER_CLASS,
        "distinct_servers": len(servers) >= MIN_DISTINCT_SERVERS,
        "class_balance": bool(
            smaller
            and imbalance_ratio is not None
            and imbalance_ratio <= MAX_CLASS_IMBALANCE_RATIO
        ),
    }
    ready = all(gates.values())

    blockers: list[str] = []
    if not gates["total_binary_labels"]:
        blockers.append(f"Need {MIN_BINARY_LABELS - len(binary)} more high-confidence binary labels")
    if not gates["positive_labels"]:
        blockers.append(f"Need {MIN_PER_CLASS - positive} more confirmed failure labels")
    if not gates["negative_labels"]:
        blockers.append(f"Need {MIN_PER_CLASS - negative} more false-positive labels")
    if not gates["distinct_servers"]:
        blockers.append(f"Need labels from {MIN_DISTINCT_SERVERS - len(servers)} more distinct servers")
    if not gates["class_balance"]:
        blockers.append(
            "Binary labels must stay within a "
            f"{MAX_CLASS_IMBALANCE_RATIO:.1f}:1 class-imbalance ratio"
        )

    return {
        "ready": ready,
        "engine": "xgboost-compatible",
        "minimum_confidence": MIN_LABEL_CONFIDENCE,
        "total_labels": len(all_rows),
        "high_confidence_labels": len(high_confidence),
        "binary_labels": len(binary),
        "confirmed_failures": positive,
        "false_positives": negative,
        "distinct_servers": len(servers),
        "components": sorted(components),
        "class_imbalance_ratio": round(imbalance_ratio, 2) if imbalance_ratio is not None else None,
        "labels_by_type": dict(sorted(labels.items())),
        "high_confidence_by_type": dict(sorted(high_conf_labels.items())),
        "gates": gates,
        "thresholds": {
            "minimum_binary_labels": MIN_BINARY_LABELS,
            "minimum_per_class": MIN_PER_CLASS,
            "minimum_distinct_servers": MIN_DISTINCT_SERVERS,
            "maximum_class_imbalance_ratio": MAX_CLASS_IMBALANCE_RATIO,
        },
        "blockers": blockers,
    }
