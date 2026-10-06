from pathlib import Path


def test_imail_intelligence_v1_contract():
    backend = Path(__file__).resolve().parents[1]
    repo = Path(__file__).resolve().parents[3]

    service = (backend / "app" / "services" / "mail_intelligence.py").read_text(encoding="utf-8")
    api = (backend / "app" / "api" / "v1" / "webmail.py").read_text(encoding="utf-8")
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

    assert "Ithute Mail Intelligence" in ui
    assert "phishing_probability" in ui
    assert "bec_probability" in ui
    assert "Explainable analysis only" in ui
    assert "does not automatically block mail" in ui
