from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.services.hardware_model_evaluation import evaluate_candidate
from app.services.hardware_model_registry import model_quality_score

MIN_NEW_VERIFIED_LABELS = 24
MIN_POSITIVE_LABELS = 8
MIN_NEGATIVE_LABELS = 8
MIN_DISTINCT_SERVERS = 3
MIN_QUALITY_SCORE_DELTA = 0.50
MIN_RETRAIN_INTERVAL_HOURS = 24


@dataclass(frozen=True)
class RetrainingEvidence:
    total: int
    positives: int
    negatives: int
    distinct_servers: int


def retraining_evidence(rows: Iterable[dict[str, Any]]) -> RetrainingEvidence:
    data = list(rows)
    positives = sum(1 for row in data if int(row.get("target") or 0) == 1)
    negatives = sum(1 for row in data if int(row.get("target") or 0) == 0)
    servers = {str(row.get("server_id") or "") for row in data if row.get("server_id")}
    return RetrainingEvidence(
        total=len(data),
        positives=positives,
        negatives=negatives,
        distinct_servers=len(servers),
    )


def retraining_readiness(rows: Iterable[dict[str, Any]], *, hours_since_last_training: float | None = None) -> dict[str, Any]:
    evidence = retraining_evidence(rows)
    interval_ok = hours_since_last_training is None or float(hours_since_last_training) >= MIN_RETRAIN_INTERVAL_HOURS
    gates = {
        "new_verified_labels": evidence.total >= MIN_NEW_VERIFIED_LABELS,
        "positive_labels": evidence.positives >= MIN_POSITIVE_LABELS,
        "negative_labels": evidence.negatives >= MIN_NEGATIVE_LABELS,
        "distinct_servers": evidence.distinct_servers >= MIN_DISTINCT_SERVERS,
        "minimum_interval": interval_ok,
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "ready": all(gates.values()),
        "evidence": {
            "total": evidence.total,
            "positives": evidence.positives,
            "negatives": evidence.negatives,
            "distinct_servers": evidence.distinct_servers,
        },
        "gates": gates,
        "blockers": blockers,
        "thresholds": {
            "minimum_new_verified_labels": MIN_NEW_VERIFIED_LABELS,
            "minimum_positive_labels": MIN_POSITIVE_LABELS,
            "minimum_negative_labels": MIN_NEGATIVE_LABELS,
            "minimum_distinct_servers": MIN_DISTINCT_SERVERS,
            "minimum_retrain_interval_hours": MIN_RETRAIN_INTERVAL_HOURS,
        },
    }


def compare_candidate_to_champion(
    evaluation_rows: Iterable[dict[str, Any]],
    *,
    champion_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evaluation = evaluate_candidate(evaluation_rows)
    candidate_metrics = dict(evaluation["candidate"])
    baseline_metrics = dict(evaluation["baseline"])
    champion = dict(champion_metrics or baseline_metrics)

    candidate_score = model_quality_score({
        **candidate_metrics,
        "expected_calibration_error": float(champion.get("expected_calibration_error") or 0.0),
        "population_stability_index": float(champion.get("population_stability_index") or 0.0),
    })
    champion_score = model_quality_score({
        **champion,
        "expected_calibration_error": float(champion.get("expected_calibration_error") or 0.0),
        "population_stability_index": float(champion.get("population_stability_index") or 0.0),
    })
    score_delta = round(candidate_score - champion_score, 3)

    offline_gate = bool(evaluation["promotion"]["eligible_for_shadow"])
    beats_champion = score_delta >= MIN_QUALITY_SCORE_DELTA
    accepted = offline_gate and beats_champion

    blockers = list(evaluation["promotion"].get("blockers") or [])
    if offline_gate and not beats_champion:
        blockers.append(
            f"Candidate quality score must improve champion by at least {MIN_QUALITY_SCORE_DELTA:.2f} points"
        )

    return {
        "accepted_for_shadow": accepted,
        "candidate_metrics": candidate_metrics,
        "champion_metrics": champion,
        "candidate_quality_score": candidate_score,
        "champion_quality_score": champion_score,
        "quality_score_delta": score_delta,
        "minimum_quality_score_delta": MIN_QUALITY_SCORE_DELTA,
        "offline_evaluation": evaluation,
        "blockers": blockers,
        "rejected_state": None if accepted else "retired_or_rolled_back",
        "next_state": "shadow" if accepted else "retired_or_rolled_back",
    }


def retraining_decision(
    new_verified_rows: Iterable[dict[str, Any]],
    evaluation_rows: Iterable[dict[str, Any]],
    *,
    champion_metrics: dict[str, Any] | None = None,
    hours_since_last_training: float | None = None,
) -> dict[str, Any]:
    readiness = retraining_readiness(
        new_verified_rows,
        hours_since_last_training=hours_since_last_training,
    )
    if not readiness["ready"]:
        return {
            "action": "wait_for_evidence",
            "readiness": readiness,
            "candidate": None,
            "reason": "Retraining evidence gates are not satisfied",
        }

    comparison = compare_candidate_to_champion(
        evaluation_rows,
        champion_metrics=champion_metrics,
    )
    return {
        "action": "register_shadow_candidate" if comparison["accepted_for_shadow"] else "reject_candidate",
        "readiness": readiness,
        "candidate": comparison,
        "reason": (
            "Candidate passed offline evaluation and improved the champion"
            if comparison["accepted_for_shadow"]
            else "Candidate failed offline safety or champion-improvement gates"
        ),
    }


def retraining_policy() -> dict[str, Any]:
    return {
        "minimum_new_verified_labels": MIN_NEW_VERIFIED_LABELS,
        "minimum_positive_labels": MIN_POSITIVE_LABELS,
        "minimum_negative_labels": MIN_NEGATIVE_LABELS,
        "minimum_distinct_servers": MIN_DISTINCT_SERVERS,
        "minimum_retrain_interval_hours": MIN_RETRAIN_INTERVAL_HOURS,
        "minimum_quality_score_delta": MIN_QUALITY_SCORE_DELTA,
        "candidate_failure_action": "retired_or_rolled_back",
        "candidate_success_action": "shadow",
        "direct_activation_allowed": False,
    }
