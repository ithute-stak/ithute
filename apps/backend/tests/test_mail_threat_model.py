from app.services.mail_threat_model import (
    artifact_sha256,
    grouped_split,
    multiclass_metrics,
    predict,
    promotion_decision,
    train_and_evaluate,
    train_model,
)


def _row(index: int, label: str, mailbox: str):
    if label == "legitimate":
        features = {
            "phishing_probability": 0.05,
            "bec_probability": 0.04,
            "intent_confidence": 0.8,
            "priority_score": 20,
            "attachment_count": 0,
            "url_count": 0,
            "money_count": 0,
            "date_count": 0,
            "reference_count": 0,
            "deadline_count": 0,
            "body_length_bucket": 2,
            "reply_needed": False,
            "has_reply_to": False,
            "signal_names": [],
        }
    elif label == "phishing":
        features = {
            "phishing_probability": 0.92,
            "bec_probability": 0.28,
            "intent_confidence": 0.9,
            "priority_score": 82,
            "attachment_count": 1,
            "url_count": 2,
            "money_count": 0,
            "date_count": 0,
            "reference_count": 0,
            "deadline_count": 1,
            "body_length_bucket": 1,
            "reply_needed": True,
            "has_reply_to": True,
            "signal_names": ["credential_request", "external_link_domain", "urgency_language"],
        }
    else:
        features = {
            "phishing_probability": 0.48,
            "bec_probability": 0.94,
            "intent_confidence": 0.92,
            "priority_score": 88,
            "attachment_count": 1,
            "url_count": 0,
            "money_count": 1,
            "date_count": 1,
            "reference_count": 1,
            "deadline_count": 1,
            "body_length_bucket": 2,
            "reply_needed": True,
            "has_reply_to": True,
            "signal_names": ["payment_language", "reply_to_domain_mismatch", "urgency_language"],
        }
    return {
        "mailbox_id": mailbox,
        "message_ref": f"msg-{index}",
        "label": label,
        "features": features,
    }


def _dataset():
    rows = []
    labels = ("legitimate", "phishing", "bec")
    for index in range(90):
        rows.append(_row(index, labels[index % 3], f"mailbox-{index % 6}"))
    return rows


def test_grouped_split_is_deterministic():
    rows = _dataset()
    first = grouped_split(rows)
    second = grouped_split(rows)

    assert [row["message_ref"] for row in first[0]] == [row["message_ref"] for row in second[0]]
    assert [row["message_ref"] for row in first[1]] == [row["message_ref"] for row in second[1]]


def test_training_artifact_is_reproducible():
    rows, _ = grouped_split(_dataset())
    first = train_model(rows)
    second = train_model(rows)

    assert first == second
    assert artifact_sha256(first) == artifact_sha256(second)


def test_model_separates_clear_mail_classes():
    rows, _ = grouped_split(_dataset())
    artifact = train_model(rows)

    legit = predict(artifact, _row(200, "legitimate", "m")["features"])
    phish = predict(artifact, _row(201, "phishing", "m")["features"])
    bec = predict(artifact, _row(202, "bec", "m")["features"])

    assert max(legit, key=legit.get) == "legitimate"
    assert max(phish, key=phish.get) == "phishing"
    assert max(bec, key=bec.get) == "bec"


def test_metrics_include_calibration_and_brier():
    rows = [
        {"label": "legitimate", "probabilities": {"legitimate": 0.9, "phishing": 0.05, "bec": 0.05}},
        {"label": "phishing", "probabilities": {"legitimate": 0.05, "phishing": 0.9, "bec": 0.05}},
        {"label": "bec", "probabilities": {"legitimate": 0.05, "phishing": 0.05, "bec": 0.9}},
    ]
    metrics = multiclass_metrics(rows)

    assert metrics["macro_precision"] == 1.0
    assert metrics["macro_recall"] == 1.0
    assert metrics["multiclass_brier"] < 0.02
    assert metrics["expected_calibration_error"] <= 0.11


def test_promotion_never_allows_direct_activation():
    decision = promotion_decision({
        "sample_count": 100,
        "macro_precision": 0.95,
        "macro_recall": 0.95,
        "multiclass_brier": 0.05,
        "expected_calibration_error": 0.04,
    })

    assert decision["eligible_for_shadow"] is True
    assert decision["eligible_for_activation"] is False
    assert decision["next_state"] == "shadow"


def test_bad_calibration_blocks_shadow():
    decision = promotion_decision({
        "sample_count": 100,
        "macro_precision": 0.95,
        "macro_recall": 0.95,
        "multiclass_brier": 0.05,
        "expected_calibration_error": 0.30,
    })

    assert decision["eligible_for_shadow"] is False


def test_train_and_evaluate_is_privacy_safe_and_versioned():
    result = train_and_evaluate(_dataset())

    assert result["raw_message_content_used"] is False
    assert result["artifact_sha256"]
    assert result["version"].startswith("mail_multiclass_logistic_v1-")
    assert result["training_rows"] > 0
    assert result["validation_rows"] >= 20



def test_grouped_split_does_not_cross_mailboxes_when_possible():
    rows = _dataset()
    train, validation = grouped_split(rows)

    train_mailboxes = {row["mailbox_id"] for row in train}
    validation_mailboxes = {row["mailbox_id"] for row in validation}

    assert train_mailboxes.isdisjoint(validation_mailboxes)
