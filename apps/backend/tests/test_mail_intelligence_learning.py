from app.services.mail_intelligence_learning import feature_snapshot, training_readiness


def _intel(phishing=0.1, bec=0.1, signals=None):
    return {
        "model": "ithute-mail-intelligence-v1",
        "security": {
            "phishing_probability": phishing,
            "bec_probability": bec,
            "recommended_action": "allow",
            "signals": signals or [],
        },
        "business": {
            "intent": {"label": "general", "confidence": 0.5},
            "priority": "normal",
            "priority_score": 20,
            "reply_needed": False,
            "entities": {
                "urls": [],
                "money": [],
                "dates": [],
                "references": [],
                "deadline_terms": [],
            },
        },
    }


def test_feature_snapshot_never_stores_raw_body():
    message = {
        "body_text": "secret message body",
        "reply_to": "",
        "attachments": [{"filename": "a.pdf"}],
    }
    snapshot = feature_snapshot(message, _intel())

    assert "secret message body" not in str(snapshot)
    assert snapshot["raw_body_stored"] is False
    assert snapshot["attachment_count"] == 1


def test_feature_snapshot_keeps_explainable_signals():
    snapshot = feature_snapshot(
        {"body_text": "x", "attachments": []},
        _intel(
            phishing=0.8,
            signals=[
                {"signal": "reply_to_domain_mismatch", "weight": 22, "evidence": ["x"]},
                {"signal": "urgency_language", "weight": 12, "evidence": ["urgent"]},
            ],
        ),
    )

    assert snapshot["phishing_probability"] == 0.8
    assert snapshot["signal_weights"]["reply_to_domain_mismatch"] == 22


def test_training_readiness_requires_enough_trusted_labels():
    rows = [{"label": "legitimate", "confidence": 0.95} for _ in range(8)]
    rows += [{"label": "phishing", "confidence": 0.95} for _ in range(8)]

    result = training_readiness(rows)

    assert result["ready"] is False
    assert result["gates"]["total_labels"] is False


def test_low_confidence_labels_do_not_count():
    rows = [{"label": "legitimate", "confidence": 0.7} for _ in range(40)]
    rows += [{"label": "phishing", "confidence": 0.7} for _ in range(40)]

    result = training_readiness(rows)

    assert result["trusted_labels"] == 0
    assert result["ready"] is False


def test_two_classes_are_not_enough_for_three_class_model():
    rows = [{"label": "legitimate", "confidence": 0.95} for _ in range(20)]
    rows += [{"label": "phishing", "confidence": 0.95} for _ in range(20)]

    result = training_readiness(rows)

    assert result["ready"] is False
    assert result["gates"]["all_three_classes"] is False


def test_balanced_verified_three_class_labels_enable_training():
    rows = [{"label": "legitimate", "confidence": 0.95} for _ in range(30)]
    rows += [{"label": "phishing", "confidence": 0.95} for _ in range(30)]
    rows += [{"label": "bec", "confidence": 0.95} for _ in range(30)]

    result = training_readiness(rows)

    assert result["ready"] is True
    assert result["class_counts"]["bec"] == 30
    assert result["raw_message_content_used"] is False
