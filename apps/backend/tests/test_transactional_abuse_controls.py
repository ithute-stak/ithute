from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_transactional_mail_verifies_tls_by_default():
    config = (ROOT / "app" / "core" / "config.py").read_text()
    assert "transactional_smtp_verify_tls: bool = True" in config
    assert 'TRANSACTIONAL_SMTP_VERIFY_TLS must be enabled in production' in config


def test_transactional_api_has_burst_abuse_limits():
    source = (ROOT / "app" / "api" / "v1" / "transactional.py").read_text()
    assert "transactional_tenant_per_minute_limit" in source
    assert "transactional_api_key_per_minute_limit" in source
    assert "per-minute tenant sending limit" in source
    assert "per-minute API key sending limit" in source
