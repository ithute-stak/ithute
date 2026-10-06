from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable

from app.services.hardware_training_dataset import TRAINING_FEATURES

ALGORITHM = "regularized_logistic_v1"
FEATURE_SCHEMA_VERSION = "hardware-v1"
TRAIN_FRACTION = 0.80
LEARNING_RATE = 0.08
EPOCHS = 600
L2_PENALTY = 0.02
EPSILON = 1e-9


@dataclass(frozen=True)
class SplitDataset:
    train: list[dict[str, Any]]
    validation: list[dict[str, Any]]


def _stable_bucket(row: dict[str, Any]) -> int:
    key = f"{row.get('server_id','')}:{row.get('snapshot_id','')}:{row.get('label_id','')}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def deterministic_split(rows: Iterable[dict[str, Any]], *, train_fraction: float = TRAIN_FRACTION) -> SplitDataset:
    data = list(rows)
    cutoff = max(1, min(99, int(round(float(train_fraction) * 100))))
    train = [row for row in data if _stable_bucket(row) < cutoff]
    validation = [row for row in data if _stable_bucket(row) >= cutoff]

    # Tiny datasets can hash entirely into one side. Keep the split deterministic
    # while ensuring evaluation exists.
    if len(data) >= 2 and not validation:
        ordered = sorted(data, key=_stable_bucket)
        validation = [ordered[-1]]
        train = ordered[:-1]
    if len(data) >= 2 and not train:
        ordered = sorted(data, key=_stable_bucket)
        train = [ordered[0]]
        validation = ordered[1:]
    return SplitDataset(train=train, validation=validation)


def _feature_value(row: dict[str, Any], name: str) -> float:
    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    value = features.get(name)
    return float(value) if value is not None else 0.0


def fit_standardizer(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, float]]:
    data = list(rows)
    stats: dict[str, dict[str, float]] = {}
    for name in TRAINING_FEATURES:
        values = [_feature_value(row, name) for row in data]
        mean = sum(values) / len(values) if values else 0.0
        variance = sum((value - mean) ** 2 for value in values) / len(values) if values else 0.0
        std = math.sqrt(variance)
        stats[name] = {"mean": round(mean, 12), "std": round(std if std > EPSILON else 1.0, 12)}
    return stats


def _vector(row: dict[str, Any], standardizer: dict[str, dict[str, float]]) -> list[float]:
    values = [1.0]
    for name in TRAINING_FEATURES:
        stat = standardizer[name]
        values.append((_feature_value(row, name) - stat["mean"]) / stat["std"])
    return values


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def train_logistic(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    if len(data) < 2:
        raise ValueError("at least two training rows are required")
    targets = {int(row.get("target") or 0) for row in data}
    if targets != {0, 1}:
        raise ValueError("training data must contain both binary classes")

    standardizer = fit_standardizer(data)
    width = 1 + len(TRAINING_FEATURES)
    weights = [0.0] * width

    for _ in range(EPOCHS):
        gradient = [0.0] * width
        for row in data:
            x = _vector(row, standardizer)
            target = int(row.get("target") or 0)
            probability = _sigmoid(sum(weight * value for weight, value in zip(weights, x)))
            error = probability - target
            for index, value in enumerate(x):
                gradient[index] += error * value
        scale = 1.0 / len(data)
        for index in range(width):
            penalty = 0.0 if index == 0 else L2_PENALTY * weights[index]
            weights[index] -= LEARNING_RATE * (gradient[index] * scale + penalty)

    return {
        "algorithm": ALGORITHM,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": list(TRAINING_FEATURES),
        "standardizer": standardizer,
        "weights": [round(weight, 12) for weight in weights],
        "hyperparameters": {
            "learning_rate": LEARNING_RATE,
            "epochs": EPOCHS,
            "l2_penalty": L2_PENALTY,
        },
    }


def predict_probability(artifact: dict[str, Any], row: dict[str, Any]) -> float:
    standardizer = artifact["standardizer"]
    weights = [float(value) for value in artifact["weights"]]
    x = _vector(row, standardizer)
    return round(_sigmoid(sum(weight * value for weight, value in zip(weights, x))), 8)


def artifact_fingerprint(artifact: dict[str, Any]) -> str:
    canonical = json.dumps(artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def dataset_fingerprint(rows: Iterable[dict[str, Any]]) -> str:
    normalized = []
    for row in rows:
        normalized.append({
            "label_id": str(row.get("label_id") or ""),
            "server_id": str(row.get("server_id") or ""),
            "snapshot_id": str(row.get("snapshot_id") or ""),
            "target": int(row.get("target") or 0),
            "features": {
                name: float((row.get("features") or {}).get(name, 0.0))
                for name in TRAINING_FEATURES
            },
        })
    normalized.sort(key=lambda item: (item["server_id"], item["snapshot_id"], item["label_id"]))
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def train_candidate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    data = list(rows)
    split = deterministic_split(data)
    if len(split.train) < 2 or len(split.validation) < 1:
        raise ValueError("dataset is too small for deterministic train/validation execution")

    artifact = train_logistic(split.train)
    artifact["dataset_fingerprint"] = dataset_fingerprint(data)
    artifact["train_rows"] = len(split.train)
    artifact["validation_rows"] = len(split.validation)
    artifact_hash = artifact_fingerprint(artifact)
    version = f"{ALGORITHM}-{artifact_hash[:12]}"

    evaluation_rows = []
    for row in split.validation:
        evaluation_rows.append({
            "target": int(row.get("target") or 0),
            "candidate_probability": predict_probability(artifact, row),
            "baseline_probability": float(row.get("baseline_probability") or 0.0),
            "server_id": str(row.get("server_id") or ""),
            "snapshot_id": str(row.get("snapshot_id") or ""),
        })

    return {
        "name": "hardware-failure-supervised",
        "version": version,
        "algorithm": ALGORITHM,
        "artifact": artifact,
        "artifact_sha256": artifact_hash,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "dataset_sha256": artifact["dataset_fingerprint"],
        "training_rows": len(split.train),
        "validation_rows": len(split.validation),
        "evaluation_rows": evaluation_rows,
    }
