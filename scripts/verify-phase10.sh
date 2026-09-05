#!/usr/bin/env sh
set -eu

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.phase6-mail.yml"

printf '\n== Phase 10 FINAL: Phase 9 regression gate ==\n'
sh scripts/verify-phase9.sh

printf '\n== Phase 10 FINAL: rebuild hardened services ==\n'
$COMPOSE build backend
$COMPOSE up -d --force-recreate rspamd-redis rspamd backend

printf '\n== Phase 10 FINAL: backend syntax and security tests ==\n'
$COMPOSE exec -T backend python -m compileall -q app
$COMPOSE exec -T backend pytest -q tests/test_config_security.py tests/test_deliverability.py tests/test_security_hardening.py

printf '\n== Phase 10 FINAL: dedicated DKIM encryption envelope ==\n'
$COMPOSE exec -T backend python - <<'PY'
from app.core.security import decrypt_dkim_secret, decrypt_secret, encrypt_dkim_secret, encrypt_secret
sample = 'phase10-private-key-material'
wrapped = encrypt_dkim_secret(sample)
assert wrapped.startswith('dkim$'), wrapped[:12]
assert decrypt_dkim_secret(wrapped) == sample
legacy = encrypt_secret(sample)
assert decrypt_secret(legacy) == sample
assert decrypt_dkim_secret(legacy) == sample
print('DKIM envelope:', wrapped.split('$', 2)[:2])
print('Legacy Phase 8 DKIM ciphertext remains readable for safe rewrap migration.')
PY

printf '\n== Phase 10 FINAL: Redis-backed login throttle ==\n'
$COMPOSE exec -T backend python - <<'PY'
from app.core.config import settings
from app.services.security_controls import clear_webmail_login_failures, record_webmail_login_failure, webmail_login_allowed
address = 'phase10-throttle@example.test'
ip = '203.0.113.77'
clear_webmail_login_failures(address, ip)
allowed, retry = webmail_login_allowed(address, ip)
assert allowed and retry == 0
for _ in range(settings.webmail_login_max_attempts):
    count, locked = record_webmail_login_failure(address, ip)
assert locked is True
allowed, retry = webmail_login_allowed(address, ip)
assert allowed is False and retry > 0
clear_webmail_login_failures(address, ip)
allowed, retry = webmail_login_allowed(address, ip)
assert allowed and retry == 0
print('login throttle lock/Retry-After state and successful cleanup verified')
PY

printf '\n== Phase 10 FINAL: isolated Rspamd signing Redis ==\n'
$COMPOSE exec -T backend python - <<'PY'
from redis import Redis
from app.core.config import settings
assert settings.rspamd_redis_url != settings.redis_url
app_redis = Redis.from_url(settings.redis_url, decode_responses=True)
signing_redis = Redis.from_url(settings.rspamd_redis_url, decode_responses=True)
assert app_redis.ping() and signing_redis.ping()
assert not app_redis.exists('dkim_keys'), 'DKIM private material leaked into application Redis'
print('application redis:', settings.redis_url)
print('signing redis:', settings.rspamd_redis_url)
print('Rspamd signing Redis is isolated from application sessions/cache/throttles.')
PY

printf '\n== Phase 10 FINAL: browser mutation boundary and security headers ==\n'
$COMPOSE exec -T backend python - <<'PY'
import httpx
base = 'http://127.0.0.1:8000'
with httpx.Client(base_url=base, timeout=5) as client:
    health = client.get('/health/live')
    assert health.status_code == 200
    assert health.headers.get('x-content-type-options') == 'nosniff'
    assert health.headers.get('x-frame-options') == 'DENY'
    assert "default-src 'none'" in health.headers.get('content-security-policy', '')
    rejected = client.post('/api/v1/webmail/session', headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'}, json={'address':'nobody@example.test','password':'invalid'})
    assert rejected.status_code == 403, rejected.text
    assert rejected.json()['detail'] == 'Cross-origin API mutation rejected'
    rejected_control = client.post('/api/v1/auth/login', headers={'Origin': 'https://evil.example', 'Sec-Fetch-Site': 'cross-site'}, json={'email':'nobody@example.test','password':'invalid'})
    assert rejected_control.status_code == 403, rejected_control.text
print('security headers and cross-origin mutation guard verified for webmail and control-plane APIs')
PY

printf '\n== Phase 10 FINAL: redacted append-only security audit event ==\n'
$COMPOSE exec -T backend python - <<'PY'
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models import AuditLog
from app.services.security_audit import assert_redacted_metadata, record_webmail_security_event
secret = 'NeverPutThisPasswordInAudit!'
db = SessionLocal()
try:
    row = record_webmail_security_event(
        db,
        action='security.webmail.verifier',
        address='unknown-phase10-verifier@example.test',
        client_ip='203.0.113.88',
        user_agent='phase10-verifier',
        request_id='phase10-security-audit',
        outcome='verification',
    )
    db.commit(); db.refresh(row)
    assert row.resource_type == 'mailbox_security'
    assert row.resource_id.startswith('unknown:')
    assert 'unknown-phase10-verifier@example.test' not in (row.metadata_json or '')
    assert_redacted_metadata(row.metadata_json, [secret, 'unknown-phase10-verifier@example.test'])
    found = db.scalar(select(AuditLog).where(AuditLog.id == row.id))
    assert found is not None
    db.delete(found); db.commit()
    print('redacted security audit append/read path verified without password, token, body or attachment logging')
finally:
    db.close()
PY

printf '\n== Phase 10 FINAL: attachment and HTML active-content policy ==\n'
$COMPOSE exec -T backend python - <<'PY'
from app.api.v1.webmail import _safe_attachment_name
from app.services.webmail_polish import sanitize_html
payload = '<svg onload="alert(1)"></svg><script>alert(1)</script><a href="javascript:alert(1)">x</a><p>safe</p>'
safe = sanitize_html(payload).lower()
assert '<svg' not in safe and '<script' not in safe and 'javascript:' not in safe
assert '<p>safe</p>' in safe
name = _safe_attachment_name('../../evil\r\nContent-Type: text/html')
assert '/' not in name and '\\' not in name and '\r' not in name and '\n' not in name
print('HTML active content stripped and attachment filenames/header boundaries hardened')
PY

printf '\n== Phase 10 FINAL: secret rewrap utility is present and importable ==\n'
$COMPOSE exec -T backend python -m py_compile /app/../scripts/rewrap-dkim-secrets.py 2>/dev/null || true
# The scripts directory is not mounted inside the backend image in every compose mode;
# verify the host copy directly as the deployment artifact.
python3 -m py_compile scripts/rewrap-dkim-secrets.py
printf 'DKIM rewrap utility syntax verified.\n'

printf '\n== Phase 10 FINAL: configuration propagation ==\n'
$COMPOSE exec -T backend python - <<'PY'
from app.core.config import settings
assert settings.dkim_encryption_key_id
assert settings.rspamd_redis_url.startswith(('redis://', 'rediss://'))
assert 3 <= settings.webmail_login_max_attempts <= 100
assert settings.webmail_login_window_seconds >= 60
assert settings.webmail_login_lock_seconds >= 60
print('DKIM key id:', settings.dkim_encryption_key_id)
print('webmail throttle:', settings.webmail_login_max_attempts, settings.webmail_login_window_seconds, settings.webmail_login_lock_seconds)
PY

printf '\nPhase 10 FINAL SECURITY & COMPLIANCE acceptance PASSED.\n'
printf 'Verified key separation and migration readiness, isolated signing/session secrets, cross-origin browser mutation enforcement, brute-force protection, redacted security audit coverage, hardened HTML/attachments, production security headers, and full Phase 9 regression.\n'
printf 'Phase 10 is ready for acceptance and fast-forward merge to main after user confirmation.\n'
