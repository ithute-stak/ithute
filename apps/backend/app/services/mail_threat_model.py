from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Iterable

CLASSES = ("legitimate", "phishing", "bec")
ALGORITHM = "mail_multiclass_logistic_v1"
EPOCHS = 700
LEARNING_RATE = 0.06
L2_PENALTY = 0.02
MIN_EVALUATION_SAMPLES = 20
MIN_MACRO_RECALL = 0.72
MIN_MACRO_PRECISION = 0.78
MAX_MULTICLASS_BRIER = 0.22
MAX_ECE = 0.12
EPSILON = 1e-9

NUMERIC_FEATURES = (
    "phishing_probability",
    "bec_probability",
    "intent_confidence",
    "priority_score",
    "behavior_score",
    "attachment_count",
    "url_count",
    "money_count",
    "date_count",
    "reference_count",
    "deadline_count",
    "body_length_bucket",
)
BOOLEAN_FEATURES = ("reply_needed", "has_reply_to", "spf_failed", "dkim_failed", "dmarc_failed")
SIGNAL_FEATURES = (
    "urgency_language",
    "credential_request",
    "payment_language",
    "threat_or_pressure",
    "reply_to_domain_mismatch",
    "external_link_domain",
    "risky_attachment_type",
    "mail_authentication_failure",
    "first_seen_sender",
    "unusual_sending_hour",
    "sender_reply_domain_changed",
    "unexpected_attachment_pattern",
    "new_payment_request_pattern",
)


def _stable_bucket(row: dict[str, Any], *, mailbox_grouped: bool) -> int:
    mailbox_id = str(row.get("mailbox_id") or "")
    message_ref = str(row.get("message_ref") or "")
    key = mailbox_id if mailbox_grouped and mailbox_id else f"{mailbox_id}:{message_ref}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 100


def grouped_split(rows: Iterable[dict[str, Any]], *, train_percent: int = 75) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = list(rows)
    cutoff = max(1, min(99, int(train_percent)))
    mailbox_count = len({str(row.get("mailbox_id") or "") for row in data if row.get("mailbox_id")})
    mailbox_grouped = mailbox_count >= 3
    train = [row for row in data if _stable_bucket(row, mailbox_grouped=mailbox_grouped) < cutoff]
    validation = [row for row in data if _stable_bucket(row, mailbox_grouped=mailbox_grouped) >= cutoff]
    if len(data) >= 2 and not validation:
        ordered = sorted(data, key=lambda row: _stable_bucket(row, mailbox_grouped=False))
        validation = [ordered[-1]]
        train = ordered[:-1]
    if len(data) >= 2 and not train:
        ordered = sorted(data, key=lambda row: _stable_bucket(row, mailbox_grouped=False))
        train = [ordered[0]]
        validation = ordered[1:]
    return train, validation


def vectorize(snapshot: dict[str, Any]) -> list[float]:
    values = [float(snapshot.get(name) or 0.0) for name in NUMERIC_FEATURES]
    values.extend(1.0 if snapshot.get(name) else 0.0 for name in BOOLEAN_FEATURES)
    signal_names = set(snapshot.get("signal_names") or []) | set(snapshot.get("behavior_signal_names") or [])
    values.extend(1.0 if name in signal_names else 0.0 for name in SIGNAL_FEATURES)
    return values


def _fit_standardizer(vectors: list[list[float]]) -> dict[str, list[float]]:
    width = len(vectors[0]) if vectors else 0
    means = []
    stds = []
    for index in range(width):
        column = [row[index] for row in vectors]
        mean = sum(column) / len(column)
        variance = sum((value - mean) ** 2 for value in column) / len(column)
        std = math.sqrt(variance)
        means.append(mean)
        stds.append(std if std > EPSILON else 1.0)
    return {"means": means, "stds": stds}


def _scale(vector: list[float], standardizer: dict[str, list[float]]) -> list[float]:
    return [
        (value - standardizer["means"][index]) / standardizer["stds"][index]
        for index, value in enumerate(vector)
    ]


def _softmax(logits: list[float]) -> list[float]:
    maximum = max(logits)
    values = [math.exp(value - maximum) for value in logits]
    total = sum(values)
    return [value / total for value in values]


def train_model(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    labels = {str(row.get("label") or "") for row in data}
    if len(data) < 2 or len(labels & set(CLASSES)) < 2:
        raise ValueError("training data must contain at least two supported classes")

    vectors = [vectorize(row.get("features") or {}) for row in data]
    standardizer = _fit_standardizer(vectors)
    width = len(vectors[0])
    weights = [[0.0] * (width + 1) for _ in CLASSES]

    for _ in range(EPOCHS):
        gradients = [[0.0] * (width + 1) for _ in CLASSES]
        for row, raw_vector in zip(data, vectors):
            x = [1.0] + _scale(raw_vector, standardizer)
            target_label = str(row.get("label") or "")
            logits = [sum(weight * value for weight, value in zip(class_weights, x)) for class_weights in weights]
            probabilities = _softmax(logits)
            for class_index, class_name in enumerate(CLASSES):
                expected = 1.0 if target_label == class_name else 0.0
                error = probabilities[class_index] - expected
                for feature_index, value in enumerate(x):
                    gradients[class_index][feature_index] += error * value

        scale = 1.0 / len(data)
        for class_index in range(len(CLASSES)):
            for feature_index in range(width + 1):
                penalty = 0.0 if feature_index == 0 else L2_PENALTY * weights[class_index][feature_index]
                weights[class_index][feature_index] -= LEARNING_RATE * (
                    gradients[class_index][feature_index] * scale + penalty
                )

    artifact = {
        "algorithm": ALGORITHM,
        "classes": list(CLASSES),
        "numeric_features": list(NUMERIC_FEATURES),
        "boolean_features": list(BOOLEAN_FEATURES),
        "signal_features": list(SIGNAL_FEATURES),
        "standardizer": {
            "means": [round(value, 12) for value in standardizer["means"]],
            "stds": [round(value, 12) for value in standardizer["stds"]],
        },
        "weights": [[round(value, 12) for value in row] for row in weights],
        "hyperparameters": {
            "epochs": EPOCHS,
            "learning_rate": LEARNING_RATE,
            "l2_penalty": L2_PENALTY,
        },
    }
    return artifact


def predict(artifact: dict[str, Any], features: dict[str, Any]) -> dict[str, float]:
    raw = vectorize(features)
    scaled = [1.0] + _scale(raw, artifact["standardizer"])
    logits = [
        sum(float(weight) * value for weight, value in zip(class_weights, scaled))
        for class_weights in artifact["weights"]
    ]
    probabilities = _softmax(logits)
    return {name: round(probability, 8) for name, probability in zip(CLASSES, probabilities)}


def multiclass_metrics(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    confusion = {label: defaultdict(int) for label in CLASSES}
    precision_values = []
    recall_values = []
    brier_total = 0.0
    confidence_rows = []

    for row in data:
        truth = str(row["label"])
        probabilities = dict(row["probabilities"])
        predicted = max(CLASSES, key=lambda label: float(probabilities.get(label) or 0.0))
        confusion[truth][predicted] += 1
        for label in CLASSES:
            target = 1.0 if truth == label else 0.0
            brier_total += (float(probabilities.get(label) or 0.0) - target) ** 2
        confidence = max(float(probabilities.get(label) or 0.0) for label in CLASSES)
        confidence_rows.append((confidence, 1.0 if predicted == truth else 0.0))

    for label in CLASSES:
        tp = confusion[label][label]
        fp = sum(confusion[truth][label] for truth in CLASSES if truth != label)
        fn = sum(confusion[label][pred] for pred in CLASSES if pred != label)
        precision_values.append(tp / (tp + fp) if tp + fp else 0.0)
        recall_values.append(tp / (tp + fn) if tp + fn else 0.0)

    ece = 0.0
    bins = 10
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        bucket = [
            (confidence, correct)
            for confidence, correct in confidence_rows
            if low <= confidence < high or (index == bins - 1 and confidence == 1.0)
        ]
        if not bucket:
            continue
        avg_confidence = sum(item[0] for item in bucket) / len(bucket)
        accuracy = sum(item[1] for item in bucket) / len(bucket)
        ece += abs(avg_confidence - accuracy) * (len(bucket) / max(1, len(confidence_rows)))

    sample_count = len(data)
    return {
        "sample_count": sample_count,
        "macro_precision": round(sum(precision_values) / len(CLASSES), 4),
        "macro_recall": round(sum(recall_values) / len(CLASSES), 4),
        "multiclass_brier": round(brier_total / max(1, sample_count * len(CLASSES)), 4),
        "expected_calibration_error": round(ece, 4),
        "confusion": {label: dict(confusion[label]) for label in CLASSES},
    }


def promotion_decision(metrics: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "sample_count": int(metrics.get("sample_count") or 0) >= MIN_EVALUATION_SAMPLES,
        "macro_precision": float(metrics.get("macro_precision") or 0.0) >= MIN_MACRO_PRECISION,
        "macro_recall": float(metrics.get("macro_recall") or 0.0) >= MIN_MACRO_RECALL,
        "multiclass_brier": float(metrics.get("multiclass_brier") if metrics.get("multiclass_brier") is not None else 1.0) <= MAX_MULTICLASS_BRIER,
        "calibration": float(metrics.get("expected_calibration_error") if metrics.get("expected_calibration_error") is not None else 1.0) <= MAX_ECE,
    }
    return {
        "eligible_for_shadow": all(gates.values()),
        "eligible_for_activation": False,
        "next_state": "shadow" if all(gates.values()) else "rejected",
        "gates": gates,
        "thresholds": {
            "minimum_evaluation_samples": MIN_EVALUATION_SAMPLES,
            "minimum_macro_precision": MIN_MACRO_PRECISION,
            "minimum_macro_recall": MIN_MACRO_RECALL,
            "maximum_multiclass_brier": MAX_MULTICLASS_BRIER,
            "maximum_expected_calibration_error": MAX_ECE,
        },
    }


def artifact_sha256(artifact: dict[str, Any]) -> str:
    canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def train_and_evaluate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    train, validation = grouped_split(data)
    if len(train) < 2 or len(validation) < 1:
        raise ValueError("not enough data for grouped holdout evaluation")

    artifact = train_model(train)
    evaluated = [
        {
            "label": str(row["label"]),
            "probabilities": predict(artifact, row.get("features") or {}),
            "mailbox_id": row.get("mailbox_id"),
            "message_ref": row.get("message_ref"),
        }
        for row in validation
    ]
    metrics = multiclass_metrics(evaluated)
    decision = promotion_decision(metrics)
    fingerprint = artifact_sha256(artifact)
    return {
        "artifact": artifact,
        "artifact_sha256": fingerprint,
        "version": f"{ALGORITHM}-{fingerprint[:12]}",
        "training_rows": len(train),
        "validation_rows": len(validation),
        "metrics": metrics,
        "promotion": decision,
        "raw_message_content_used": False,
    }
