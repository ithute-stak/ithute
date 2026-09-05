from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from database.config.config import settings
from services import ithute_auth, ithute_push


class FakeJwks:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token: str):
        return SimpleNamespace(key=self.key)


def central_token(private_key, *, token_use: str, audience: str = 'ithute-pay', nonce: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        'iss': 'https://auth.ithute.co.ls',
        'sub': str(uuid4()),
        'aud': audience,
        'sid': str(uuid4()),
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(minutes=10)).timestamp()),
        'token_use': token_use,
    }
    if token_use == 'access':
        payload['nbf'] = int(now.timestamp())
    if token_use == 'id':
        payload['nonce'] = nonce or 'nonce-value'
    return jwt.encode(payload, private_key, algorithm='RS256', headers={'kid': 'test-key'})


def test_central_access_token_requires_ithute_pay_audience(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_ENABLED', True)
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_ISSUER', 'https://auth.ithute.co.ls')
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_AUDIENCE', 'ithute-pay')

    valid = central_token(private_key, token_use='access')
    claims = ithute_auth.decode_access_token(valid, jwks_client=FakeJwks(private_key.public_key()))
    assert claims['aud'] == 'ithute-pay'
    assert claims['token_use'] == 'access'

    wrong_audience = central_token(private_key, token_use='access', audience='mailbox-dns')
    with pytest.raises(jwt.InvalidAudienceError):
        ithute_auth.decode_access_token(wrong_audience, jwks_client=FakeJwks(private_key.public_key()))


def test_central_id_token_requires_exact_nonce(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_ENABLED', True)
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_ISSUER', 'https://auth.ithute.co.ls')
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_AUDIENCE', 'ithute-pay')
    token = central_token(private_key, token_use='id', nonce='expected-nonce')

    claims = ithute_auth.decode_id_token(token, nonce='expected-nonce', jwks_client=FakeJwks(private_key.public_key()))
    assert claims['nonce'] == 'expected-nonce'
    with pytest.raises(jwt.InvalidTokenError):
        ithute_auth.decode_id_token(token, nonce='other-nonce', jwks_client=FakeJwks(private_key.public_key()))


def test_push_uses_short_lived_service_token_contract(monkeypatch):
    monkeypatch.setattr(settings, 'ITHUTE_PUSH_ENABLED', True)
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_AUDIENCE', 'ithute-pay')
    monkeypatch.setattr(settings, 'ITHUTE_AUTH_ISSUER', 'https://auth.ithute.co.ls')
    monkeypatch.setattr(settings, 'ITHUTE_PUSH_URL', 'https://push.ithute.co.ls')
    monkeypatch.setattr(settings, 'ITHUTE_PUSH_SERVICE_CLIENT_SECRET', 'x' * 32)
    monkeypatch.setattr(ithute_push, '_cached_service_token', '')
    monkeypatch.setattr(ithute_push, '_cached_service_token_until', 0.0)

    calls = []

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    def fake_post(url, *, json=None, headers=None, timeout=None):
        calls.append((url, json, headers, timeout))
        if url.endswith('/v1/auth/service-token'):
            assert json == {
                'client_id': 'ithute-pay',
                'client_secret': 'x' * 32,
                'audience': 'ithute-push',
                'scope': 'push.send',
            }
            return Response({'access_token': 'service-token', 'expires_in': 300, 'scope': 'push.send'})
        assert url == 'https://push.ithute.co.ls/v1/messages'
        assert headers['Authorization'] == 'Bearer service-token'
        assert json['recipient_sub']
        return Response({'id': str(uuid4()), 'status': 'queued', 'delivery_count': 1})

    monkeypatch.setattr(ithute_push.httpx, 'post', fake_post)
    result = ithute_push.send_notification(
        recipient_sub=str(uuid4()),
        title='Payment received',
        body='M500 received',
        route='/dashboard/payments',
    )
    assert result['status'] == 'queued'
    assert len(calls) == 2
