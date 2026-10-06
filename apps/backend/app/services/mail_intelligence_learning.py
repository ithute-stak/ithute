from __future__ import annotations

from collections import Counter
from typing import Any

LABELS = {"legitimate", "phishing", "bec"}
MIN_LABEL_CONFIDENCE = 0.80
MIN_TRAINING_LABELS = 90
MIN_PER_CLASS = 20


def feature_snapshot(message: dict[str, Any], intelligence: dict[str, Any]) -> dict[str, Any]:
    security = intelligence.get("security") if isinstance(intelligence.get("security"), dict) else {}
    business = intelligence.get("business") if isinstance(intelligence.get("business"), dict) else {}
    behavior = intelligence.get("behavior") if isinstance(intelligence.get("behavior"), dict) else {}
    entities = business.get("entities") if isinstance(business.get("entities"), dict) else {}
    signals = security.get("signals") if isinstance(security.get("signals"), list) else []

    return {
        "model": str(intelligence.get("model") or ""),
        "phishing_probability": float(security.get("phishing_probability") or 0.0),
        "bec_probability": float(security.get("bec_probability") or 0.0),
        "recommended_action": str(security.get("recommended_action") or "allow"),
        "signal_names": [
            str(item.get("signal") or "")
            for item in signals
            if isinstance(item, dict) and item.get("signal")
        ],
        "signal_weights": {
            str(item.get("signal") or ""): int(item.get("weight") or 0)
            for item in signals
            if isinstance(item, dict) and item.get("signal")
        },
        "intent": str((business.get("intent") or {}).get("label") or "general"),
        "intent_confidence": float((business.get("intent") or {}).get("confidence") or 0.0),
        "priority": str(business.get("priority") or "normal"),
        "priority_score": int(business.get("priority_score") or 0),
        "behavior_score": int(behavior.get("score") or 0),
        "behavior_state": str(behavior.get("state") or "unknown"),
        "behavior_signal_names": [
            str(item.get("signal") or "")
            for item in (behavior.get("signals") or [])
            if isinstance(item, dict) and item.get("signal")
        ],
        "reply_needed": bool(business.get("reply_needed")),
        "attachment_count": len(message.get("attachments") or []),
        "url_count": len(entities.get("urls") or []),
        "money_count": len(entities.get("money") or []),
        "date_count": len(entities.get("dates") or []),
        "reference_count": len(entities.get("references") or []),
        "deadline_count": len(entities.get("deadline_terms") or []),
        "has_reply_to": bool(str(message.get("reply_to") or "").strip()),
        "spf_failed": (
            "spf=fail" in str(message.get("authentication_results") or "").lower()
            or str(message.get("received_spf") or "").lower().startswith("fail")
        ),
        "dkim_failed": "dkim=fail" in str(message.get("authentication_results") or "").lower(),
        "dmarc_failed": "dmarc=fail" in str(message.get("authentication_results") or "").lower(),
        "body_length_bucket": min(20, len(str(message.get("body_text") or "")) // 500),
        "raw_body_stored": False,
    }


def training_readiness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trusted = [
        row for row in rows
        if str(row.get("label") or "") in LABELS
        and float(row.get("confidence") or 0.0) >= MIN_LABEL_CONFIDENCE
    ]
    counts = Counter(str(row["label"]) for row in trusted)
    represented = [label for label in LABELS if counts[label] > 0]
    class_gate = all(counts[label] >= MIN_PER_CLASS for label in LABELS)
    gates = {
        "total_labels": len(trusted) >= MIN_TRAINING_LABELS,
        "all_three_classes": set(represented) == LABELS,
        "minimum_per_class": class_gate,
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "ready": all(gates.values()),
        "trusted_labels": len(trusted),
        "class_counts": {label: counts[label] for label in sorted(LABELS)},
        "represented_classes": sorted(represented),
        "gates": gates,
        "blockers": blockers,
        "thresholds": {
            "minimum_label_confidence": MIN_LABEL_CONFIDENCE,
            "minimum_training_labels": MIN_TRAINING_LABELS,
            "minimum_per_class": MIN_PER_CLASS,
        },
        "raw_message_content_used": False,
    }
