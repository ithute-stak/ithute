from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config import settings as app_settings
from app.services.ithute_auth import decode_ithute_access_token, get_ithute_auth_settings


class IthutePlatformAdminSettings(BaseSettings):
    auth_callback_url: str = "http://localhost:8006/api/v1/platform/ithute/admin/callback"
    panel_return_url: str = "http://localhost:3006/ithute-platform"
    push_url: str = "http://ithute-push:8080"
    request_timeout_seconds: float = 5.0
    step_up_seconds: int = 600
    admin_cookie_name: str = "ithute_platform_admin"
    state_cookie_name: str = "ithute_platform_admin_state"

    model_config = SettingsConfigDict(env_prefix="ITHUTE_PLATFORM_", case_sensitive=False, extra="ignore")


@lru_cache(maxsize=1)
def get_platform_admin_settings() -> IthutePlatformAdminSettings:
    return IthutePlatformAdminSettings()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def pkce_pair() -> tuple[str, str]:
    verifier = _b64(secrets.token_bytes(48))
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def sign_step_up_state(*, local_user_id: str, auth_user_id: str, state: str, nonce: str, verifier: str) -> str:
    cfg = get_platform_admin_settings()
    payload = {
        "local_user_id": local_user_id,
        "auth_user_id": auth_user_id,
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "exp": int(time.time()) + min(max(cfg.step_up_seconds, 120), 900),
    }
    encoded = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(app_settings.secret_key.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64(signature)}"


def verify_step_up_state(value: str) -> dict[str, Any]:
    try:
        encoded, supplied = value.split(".", 1)
        expected = hmac.new(app_settings.secret_key.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(supplied)):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(encoded))
    except Exception as exc:
        raise ValueError("invalid platform admin state") from exc
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("expired platform admin state")
    for key in ("local_user_id", "auth_user_id", "state", "nonce", "verifier"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise ValueError("incomplete platform admin state")
    return payload


def authorization_url(*, state: str, nonce: str, challenge: str) -> str:
    auth = get_ithute_auth_settings()
    cfg = get_platform_admin_settings()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": auth.audience,
            "redirect_uri": cfg.auth_callback_url,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "nonce": nonce,
            "scope": "openid profile email phone",
        }
    )
    return f"{auth.resolved_issuer}/v1/admin/authorize?{query}"


def exchange_code(*, code: str, verifier: str) -> dict[str, Any]:
    auth = get_ithute_auth_settings()
    cfg = get_platform_admin_settings()
    with httpx.Client(timeout=cfg.request_timeout_seconds) as client:
        response = client.post(
            f"{auth.resolved_issuer}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": auth.audience,
                "code": code,
                "redirect_uri": cfg.auth_callback_url,
                "code_verifier": verifier,
            },
        )
    if response.status_code != 200:
        raise RuntimeError("central admin authorization code exchange failed")
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise RuntimeError("central admin authorization response is invalid")
    return payload


def validate_id_token(token: str, *, nonce: str) -> dict[str, Any]:
    auth = get_ithute_auth_settings()
    signing_key = PyJWKClient(auth.resolved_jwks_url).get_signing_key_from_jwt(token).key
    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        issuer=auth.resolved_issuer,
        audience=auth.audience,
        options={"require": ["iss", "sub", "aud", "sid", "iat", "exp", "nonce", "token_use"]},
    )
    if claims.get("token_use") != "id" or not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise jwt.InvalidTokenError("invalid central admin identity token")
    return claims


def validate_admin_access_token(token: str, *, expected_sub: str) -> dict[str, Any]:
    claims = decode_ithute_access_token(token)
    if not hmac.compare_digest(str(claims.get("sub", "")), expected_sub):
        raise jwt.InvalidTokenError("central admin identity does not match linked platform owner")
    return claims


def auth_request(method: str, path: str, *, token: str, json_body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> httpx.Response:
    cfg = get_platform_admin_settings()
    auth = get_ithute_auth_settings()
    with httpx.Client(timeout=cfg.request_timeout_seconds) as client:
        return client.request(
            method,
            f"{auth.resolved_issuer}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=json_body,
            params=params,
        )


def push_admin_token(central_access_token: str) -> str:
    response = auth_request("POST", "/v1/admin/push-token", token=central_access_token)
    if response.status_code != 200:
        raise PermissionError("central Auth refused Push admin delegation")
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("central Auth returned an invalid Push admin delegation")
    return token


def push_request(method: str, path: str, *, central_access_token: str) -> httpx.Response:
    cfg = get_platform_admin_settings()
    delegated = push_admin_token(central_access_token)
    with httpx.Client(timeout=cfg.request_timeout_seconds) as client:
        return client.request(
            method,
            f"{cfg.push_url.rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {delegated}"},
        )
