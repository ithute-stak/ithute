from __future__ import annotations

from math import isfinite
from typing import Any, Iterable


MIN_EVALUATION_SAMPLES = 20
MIN_PRECISION = 0.80
MIN_RECALL = 0.70
MAX_FALSE_POSITIVE_RATE = 0.15
MAX_BRIER_SCORE = 0.20
MAX_F1_REGRESSION = 0.00
MAX_BRIER_REGRESSION = 0.00
DEFAULT_THRESHOLD = 0.50


def _probability(value: Any) -> float:
    number = float(value)
    if not isfinite(number):
        raise ValueError("model probability must be finite")
    return max(0.0, min(1.0, number))


def classification_metrics(rows: Iterable[dict[str, Any]], *, probability_key: str, threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    data = list(rows)
    threshold = max(0.0, min(1.0, float(threshold)))
    tp = tn = fp = fn = 0
    brier_sum = 0.0

    for row in data:
        target = int(row.get("target") or 0)
        if target not in {0, 1}:
            raise ValueError("target must be binary")
        probability = _probability(row.get(probability_key))
        predicted = 1 if probability >= threshold else 0
        if predicted == 1 and target == 1:
            tp += 1
        elif predicted == 0 and target == 0:
            tn += 1
        elif predicted == 1 and target == 0:
            fp += 1
        else:
            fn += 1
        brier_sum += (probability - target) ** 2

    sample_count = len(data)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / sample_count if sample_count else 0.0
    brier = brier_sum / sample_count if sample_count else 1.0

    return {
        "sample_count": sample_count,
        "threshold": round(threshold, 4),
        "confusion_matrix": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "false_positive_rate": round(false_positive_rate, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "brier_score": round(brier, 4),
    }


def promotion_decision(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "sample_count": int(candidate.get("sample_count") or 0) >= MIN_EVALUATION_SAMPLES,
        "precision": float(candidate.get("precision") or 0.0) >= MIN_PRECISION,
        "recall": float(candidate.get("recall") or 0.0) >= MIN_RECALL,
        "false_positive_rate": float(candidate.get("false_positive_rate") or 1.0) <= MAX_FALSE_POSITIVE_RATE,
        "brier_score": float(candidate.get("brier_score") or 1.0) <= MAX_BRIER_SCORE,
        "f1_no_regression": float(candidate.get("f1") or 0.0) >= float(baseline.get("f1") or 0.0) - MAX_F1_REGRESSION,
        "brier_no_regression": float(candidate.get("brier_score") or 1.0) <= float(baseline.get("brier_score") or 1.0) + MAX_BRIER_REGRESSION,
    }
    blockers: list[str] = []
    if not gates["sample_count"]:
        blockers.append(f"Need at least {MIN_EVALUATION_SAMPLES} held-out labeled samples")
    if not gates["precision"]:
        blockers.append(f"Precision must be at least {MIN_PRECISION:.0%}")
    if not gates["recall"]:
        blockers.append(f"Recall must be at least {MIN_RECALL:.0%}")
    if not gates["false_positive_rate"]:
        blockers.append(f"False-positive rate must be at most {MAX_FALSE_POSITIVE_RATE:.0%}")
    if not gates["brier_score"]:
        blockers.append(f"Brier score must be at most {MAX_BRIER_SCORE:.2f}")
    if not gates["f1_no_regression"]:
        blockers.append("Candidate F1 must not regress versus the current ensemble baseline")
    if not gates["brier_no_regression"]:
        blockers.append("Candidate calibration must not regress versus the current ensemble baseline")

    return {
        "eligible_for_shadow": all(gates.values()),
        "eligible_for_activation": False,
        "activation_reason": "A passing candidate must first run in shadow mode on live telemetry before activation",
        "gates": gates,
        "blockers": blockers,
        "thresholds": {
            "minimum_evaluation_samples": MIN_EVALUATION_SAMPLES,
            "minimum_precision": MIN_PRECISION,
            "minimum_recall": MIN_RECALL,
            "maximum_false_positive_rate": MAX_FALSE_POSITIVE_RATE,
            "maximum_brier_score": MAX_BRIER_SCORE,
            "maximum_f1_regression": MAX_F1_REGRESSION,
            "maximum_brier_regression": MAX_BRIER_REGRESSION,
        },
    }


def evaluate_candidate(rows: Iterable[dict[str, Any]], *, threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    data = list(rows)
    candidate = classification_metrics(data, probability_key="candidate_probability", threshold=threshold)
    baseline = classification_metrics(data, probability_key="baseline_probability", threshold=threshold)
    return {
        "candidate": candidate,
        "baseline": baseline,
        "promotion": promotion_decision(candidate, baseline),
    }



def promotion_policy() -> dict[str, Any]:
    return {
        "eligible_for_activation": False,
        "activation_rule": "Candidate must pass held-out evaluation and then complete live shadow validation before activation",
        "thresholds": {
            "minimum_evaluation_samples": MIN_EVALUATION_SAMPLES,
            "minimum_precision": MIN_PRECISION,
            "minimum_recall": MIN_RECALL,
            "maximum_false_positive_rate": MAX_FALSE_POSITIVE_RATE,
            "maximum_brier_score": MAX_BRIER_SCORE,
            "maximum_f1_regression": MAX_F1_REGRESSION,
            "maximum_brier_regression": MAX_BRIER_REGRESSION,
        },
    }
