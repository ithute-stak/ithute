from app.services.hardware_retraining_controller import (
    compare_candidate_to_champion,
    retraining_decision,
    retraining_policy,
    retraining_readiness,
)


def _evidence(target: int, server_id: str):
    return {"target": target, "server_id": server_id}


def _eval_row(target: int, candidate: float, baseline: float):
    return {
        "target": target,
        "candidate_probability": candidate,
        "baseline_probability": baseline,
    }


def test_retraining_waits_for_enough_new_verified_evidence():
    rows = [_evidence(1, "server-1") for _ in range(6)]
    rows += [_evidence(0, "server-2") for _ in range(6)]

    result = retraining_readiness(rows, hours_since_last_training=48)

    assert result["ready"] is False
    assert result["gates"]["new_verified_labels"] is False


def test_retraining_requires_class_balance_and_multiple_servers():
    rows = [_evidence(1, "server-1") for _ in range(24)]

    result = retraining_readiness(rows, hours_since_last_training=48)

    assert result["ready"] is False
    assert result["gates"]["negative_labels"] is False
    assert result["gates"]["distinct_servers"] is False


def test_retraining_respects_minimum_interval():
    rows = []
    for index in range(12):
        rows.append(_evidence(1, f"server-{index % 3}"))
        rows.append(_evidence(0, f"server-{index % 3}"))

    result = retraining_readiness(rows, hours_since_last_training=2)

    assert result["ready"] is False
    assert result["gates"]["minimum_interval"] is False


def test_stronger_candidate_is_admitted_to_shadow_only():
    rows = []
    for _ in range(12):
        rows.append(_eval_row(1, 0.95, 0.75))
    for _ in range(12):
        rows.append(_eval_row(0, 0.05, 0.25))

    result = compare_candidate_to_champion(rows)

    assert result["accepted_for_shadow"] is True
    assert result["next_state"] == "shadow"


def test_weaker_candidate_is_auto_rejected():
    rows = []
    for _ in range(12):
        rows.append(_eval_row(1, 0.70, 0.95))
    for _ in range(12):
        rows.append(_eval_row(0, 0.30, 0.05))

    result = compare_candidate_to_champion(rows)

    assert result["accepted_for_shadow"] is False
    assert result["next_state"] == "retired_or_rolled_back"


def test_controller_rejects_candidate_even_when_retraining_evidence_is_ready():
    evidence = []
    for index in range(12):
        evidence.append(_evidence(1, f"server-{index % 3}"))
        evidence.append(_evidence(0, f"server-{index % 3}"))

    evaluation = []
    for _ in range(12):
        evaluation.append(_eval_row(1, 0.70, 0.95))
    for _ in range(12):
        evaluation.append(_eval_row(0, 0.30, 0.05))

    result = retraining_decision(
        evidence,
        evaluation,
        hours_since_last_training=48,
    )

    assert result["action"] == "reject_candidate"
    assert result["candidate"]["rejected_state"] == "retired_or_rolled_back"


def test_retraining_policy_never_allows_direct_activation():
    policy = retraining_policy()

    assert policy["direct_activation_allowed"] is False
    assert policy["candidate_success_action"] == "shadow"
    assert policy["candidate_failure_action"] == "retired_or_rolled_back"
