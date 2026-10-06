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
