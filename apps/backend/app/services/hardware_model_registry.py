from __future__ import annotations

from typing import Any

LIFECYCLE_ORDER = (
    "candidate",
    "shadow",
    "qualified",
    "canary",
    "active",
    "retired_or_rolled_back",
)

ALLOWED_TRANSITIONS = {
    "candidate": {"shadow", "retired_or_rolled_back"},
    "shadow": {"qualified", "retired_or_rolled_back"},
    "qualified": {"canary", "retired_or_rolled_back"},
    "canary": {"active", "retired_or_rolled_back"},
    "active": {"retired_or_rolled_back"},
    "retired_or_rolled_back": set(),
}


def validate_transition(current: str, target: str) -> dict[str, Any]:
    current = str(current or "").strip()
    target = str(target or "").strip()
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    valid = target in allowed
    return {
        "valid": valid,
        "current": current,
        "target": target,
        "allowed_targets": sorted(allowed),
        "reason": "" if valid else f"Transition {current!r} -> {target!r} is not allowed",
    }


def model_quality_score(metrics: dict[str, Any]) -> float:
    precision = max(0.0, min(1.0, float(metrics.get("precision") or 0.0)))
    recall = max(0.0, min(1.0, float(metrics.get("recall") or 0.0)))
    f1 = max(0.0, min(1.0, float(metrics.get("f1") or 0.0)))
    brier = max(0.0, min(1.0, float(metrics.get("brier_score") or 1.0)))
    ece = max(0.0, min(1.0, float(metrics.get("expected_calibration_error") or 1.0)))
    fpr = max(0.0, min(1.0, float(metrics.get("false_positive_rate") or 1.0)))
    psi = max(0.0, min(1.0, float(metrics.get("population_stability_index") or 1.0)))

    # Safety-weighted score. Recall and false-positive control are deliberately
    # weighted more heavily than raw accuracy for hardware-failure prediction.
    score = (
        recall * 0.25
        + precision * 0.20
        + f1 * 0.20
        + (1.0 - fpr) * 0.15
        + (1.0 - brier) * 0.10
        + (1.0 - ece) * 0.05
        + (1.0 - psi) * 0.05
    )
    return round(score * 100.0, 3)


def registry_summary(models: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {state: 0 for state in LIFECYCLE_ORDER}
    ranked: list[dict[str, Any]] = []
    for raw in models:
        item = dict(raw)
        state = str(item.get("lifecycle_state") or "candidate")
        counts[state] = counts.get(state, 0) + 1
        metrics = item.get("shadow_metrics") if isinstance(item.get("shadow_metrics"), dict) else {}
        item["quality_score"] = model_quality_score(metrics)
        ranked.append(item)

    ranked.sort(
        key=lambda item: (
            item.get("lifecycle_state") == "active",
            float(item.get("quality_score") or 0.0),
        ),
        reverse=True,
    )
    return {
        "total_models": len(models),
        "counts": counts,
        "active_model": next((item for item in ranked if item.get("lifecycle_state") == "active"), None),
        "ranked_models": ranked,
    }
