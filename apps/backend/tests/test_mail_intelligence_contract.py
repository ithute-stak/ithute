from pathlib import Path


def test_imail_intelligence_v1_contract():
    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]

    service = (backend / "app" / "services" / "mail_intelligence.py").read_text(encoding="utf-8")
    api = (backend / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")
    webmail_service = (backend / "app" / "services" / "webmail.py").read_text(encoding="utf-8")
    ui = (repo / "apps" / "frontend" / "app" / "webmail" / "hosted-workspace.tsx").read_text(encoding="utf-8")

    assert "def analyze_mail_message" in service
    assert '"model": "ithute-mail-intelligence-v1"' in service
    assert '"automatic_blocking": False' in service
    assert '"training_use": False' in service
    assert "reply_to_domain_mismatch" in service
    assert "risky_attachment_type" in service

    assert '@router.get("/messages/{uid}/intelligence")' in api
    assert '@router.get("/intelligence")' in api
    assert 'limit: int = Query(default=20, ge=1, le=25)' in api
    assert 'payload["intelligence"] = analyze_mail_message' in api
    assert "messages_with_bodies" in api
    assert "def messages_with_bodies" in webmail_service
    assert 'mark_seen=False' in webmail_service
    assert 'readonly=True' in webmail_service

    assert "Ithute Mail Intelligence" in ui
    assert "phishing_probability" in ui
    assert "bec_probability" in ui
    assert "Explainable analysis only" in ui
    assert "does not automatically block mail" in ui



def test_imail_intelligence_learning_contract():
    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]

    api = (backend / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")
    learning = (backend / "app" / "services" / "mail_intelligence_learning.py").read_text(encoding="utf-8")
    ui = (repo / "apps" / "frontend" / "app" / "webmail" / "hosted-workspace.tsx").read_text(encoding="utf-8")

    assert '@router.post("/messages/{uid}/intelligence/verdict")' in api
    assert "Verified mail intelligence verdict is immutable" in api
    assert "mail_intelligence_training_label" in api
    assert '"raw_body_stored": False' in learning
    assert "def training_readiness" in learning
    assert "MIN_LABEL_CONFIDENCE = 0.80" in learning

    assert "Verified verdict" in ui
    assert 'saveIntelligenceVerdict("legitimate")' in ui
    assert 'saveIntelligenceVerdict("phishing")' in ui
    assert 'saveIntelligenceVerdict("bec")' in ui
    assert "Raw message content is not stored" in ui



def test_imail_supervised_threat_model_contract():
    backend = Path(__file__).resolve().parents[1]

    service = (backend / "app" / "services" / "mail_threat_model.py").read_text(encoding="utf-8")
    learning = (backend / "app" / "services" / "mail_intelligence_learning.py").read_text(encoding="utf-8")
    api = (backend / "app" / "api" / "v1" / "mail_intelligence.py").read_text(encoding="utf-8")
    models = (backend / "app" / "models" / "mail_intelligence.py").read_text(encoding="utf-8")
    migration = (backend / "alembic" / "versions" / "0089_mail_threat_models.py").read_text(encoding="utf-8")

    assert 'ALGORITHM = "mail_multiclass_logistic_v1"' in service
    assert "def grouped_split" in service
    assert "def multiclass_metrics" in service
    assert "expected_calibration_error" in service
    assert '"eligible_for_activation": False' in service
    assert 'MIN_TRAINING_LABELS = 90' in learning
    assert 'MIN_PER_CLASS = 20' in learning
    assert '"all_three_classes"' in learning

    assert '@router.post("/tenants/{tenant_id}/threat-models/train"' in api
    assert '@router.get("/tenants/{tenant_id}/threat-models")' in api
    assert '"mail.manage"' in api
    assert 'lifecycle_state = "shadow" if result["promotion"]["eligible_for_shadow"] else "rejected"' in api

    assert "class MailThreatModelVersion" in models
    assert "tenant_id" in migration
    assert "uq_mail_threat_model_tenant_name_version" in migration



def test_imail_live_shadow_contract():
    backend = Path(__file__).resolve().parents[1]

    service = (backend / "app" / "services" / "mail_threat_shadow.py").read_text(encoding="utf-8")
    webmail_api = (backend / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")
    mail_api = (backend / "app" / "api" / "v1" / "mail_intelligence.py").read_text(encoding="utf-8")
    models = (backend / "app" / "models" / "mail_intelligence.py").read_text(encoding="utf-8")
    migration = (backend / "alembic" / "versions" / "0090_mail_threat_shadow.py").read_text(encoding="utf-8")

    assert "def shadow_validation" in service
    assert "def rollback_decision" in service
    assert "population_stability_index" in service
    assert '"eligible_for_activation": False' in service
    assert '"direct_activation_allowed": False' in service
    assert '"canary_fraction": 0.05' in service

    assert "def _shadow_score_message" in webmail_api
    assert "supervised_shadow" in webmail_api
    assert "def _resolve_shadow_predictions" in webmail_api
    assert "fallback" in webmail_api

    assert '@router.get("/tenants/{tenant_id}/threat-models/{model_id}/shadow-status")' in mail_api
    assert '@router.post("/tenants/{tenant_id}/threat-models/{model_id}/qualify")' in mail_api
    assert "Only shadow models can be qualified" in mail_api

    assert "class MailThreatShadowPrediction" in models
    assert "0090_mail_threat_shadow" in migration



def test_imail_sender_behaviour_contract():
    backend = Path(__file__).resolve().parents[1]

    behavior = (backend / "app" / "services" / "mail_sender_behavior.py").read_text(encoding="utf-8")
    learning = (backend / "app" / "services" / "mail_intelligence_learning.py").read_text(encoding="utf-8")
    model = (backend / "app" / "services" / "mail_threat_model.py").read_text(encoding="utf-8")
    api = (backend / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")

    assert "first_seen_sender" in behavior
    assert "unusual_sending_hour" in behavior
    assert "sender_reply_domain_changed" in behavior
    assert "new_payment_request_pattern" in behavior
    assert '"raw_body_stored": False' in behavior
    assert "hashlib.sha256(identity)" in behavior
    assert "message_ref_hash" in behavior

    assert '"behavior_score"' in learning
    assert '"behavior_signal_names"' in learning
    assert '"behavior_score"' in model
    assert '"sender_reply_domain_changed"' in model

    assert "observe_sender_behavior" in api
    assert 'intelligence["behavior"] = behavior' in api



def test_imail_shadow_and_behavior_ui_contract():
    repo = Path(__file__).resolve().parents[3]
    ui = (repo / "apps" / "frontend" / "app" / "webmail" / "hosted-workspace.tsx").read_text(encoding="utf-8")

    assert "Sender behaviour" in ui
    assert "Supervised threat model · shadow" in ui
    assert "does not control mail delivery" in ui
    assert "heuristic fallback remains active" in ui
    assert "supervised_shadow" in ui
    assert "behavior?" in ui



def test_imail_canary_activation_and_rollback_contract():
    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]

    service = (backend / "app" / "services" / "mail_threat_canary.py").read_text(encoding="utf-8")
    webmail_api = (backend / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")
    mail_api = (backend / "app" / "api" / "v1" / "mail_intelligence.py").read_text(encoding="utf-8")
    ui = (repo / "apps" / "frontend" / "app" / "webmail" / "hosted-workspace.tsx").read_text(encoding="utf-8")
    migration = (backend / "alembic" / "versions" / "0091_mail_threat_canary.py").read_text(encoding="utf-8")

    assert "def deterministic_canary_member" in service
    assert "CANARY_FRACTION = 0.05" in service
    assert "def baseline_floor" in service
    assert '"canary_can_reduce_risk": False' in service
    assert "def automatic_rollback" in service

    assert "def _automatic_rollback_models" in webmail_api
    assert "baseline_floor" in webmail_api
    assert "canary_applied" in webmail_api
    assert "baseline_preserved" in webmail_api

    assert '@router.post("/tenants/{tenant_id}/threat-models/{model_id}/canary/start")' in mail_api
    assert '@router.get("/tenants/{tenant_id}/threat-models/{model_id}/canary-status")' in mail_api
    assert '@router.post("/tenants/{tenant_id}/threat-models/{model_id}/activate")' in mail_api
    assert "Only qualified models can enter canary" in mail_api
    assert "Only canary models can be activated" in mail_api
    assert 'previous.lifecycle_state = "retired"' in mail_api

    assert "canary_started_at" in migration
    assert "baseline cannot be weakened" in ui
    assert 'lifecycle_state || "shadow"' in ui
