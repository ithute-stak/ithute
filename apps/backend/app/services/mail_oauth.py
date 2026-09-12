from __future__ import annotations

import base64
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
import redis

from app.core.config import settings
from app.core.security import hash_token


class MailOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthProviderConfig:
    key: str
    name: str
    client_id: str
    client_secret: str
    redirect_uri: str
    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    imap_host: str
    smtp_host: str

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _google() -> OAuthProviderConfig:
    return OAuthProviderConfig(
        key="google",
        name="Google / Gmail",
        client_id=_env("WEBMAIL_GOOGLE_CLIENT_ID"),
        client_secret=_env("WEBMAIL_GOOGLE_CLIENT_SECRET"),
        redirect_uri=_env("WEBMAIL_GOOGLE_REDIRECT_URI"),
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes=("openid", "email", "profile", "https://mail.google.com/"),
        imap_host="imap.gmail.com",
        smtp_host="smtp.gmail.com",
    )


def _microsoft() -> OAuthProviderConfig:
    tenant = _env("WEBMAIL_MICROSOFT_TENANT") or "common"
    base = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
    return OAuthProviderConfig(
        key="microsoft",
        name="Microsoft 365 / Outlook",
        client_id=_env("WEBMAIL_MICROSOFT_CLIENT_ID"),
        client_secret=_env("WEBMAIL_MICROSOFT_CLIENT_SECRET"),
        redirect_uri=_env("WEBMAIL_MICROSOFT_REDIRECT_URI"),
        authorize_url=f"{base}/authorize",
        token_url=f"{base}/token",
        scopes=(
            "openid",
            "profile",
            "email",
            "offline_access",
            "https://outlook.office.com/IMAP.AccessAsUser.All",
            "https://outlook.office.com/SMTP.Send",
        ),
        imap_host="outlook.office365.com",
        smtp_host="smtp.office365.com",
    )


def provider_config(provider: str) -> OAuthProviderConfig:
    key = (provider or "").strip().lower()
    if key in {"google", "gmail", "google-workspace"}:
        return _google()
    if key in {"microsoft", "microsoft365", "office365", "outlook"}:
        return _microsoft()
    raise MailOAuthError("This mail provider does not support OAuth connection yet")


def provider_capabilities() -> list[dict[str, Any]]:
    rows = []
    for item in (_google(), _microsoft()):
        rows.append(
            {
                "provider": item.key,
                "name": item.name,
                "configured": item.configured,
                "imap_host": item.imap_host,
                "smtp_host": item.smtp_host,
            }
        )
    return rows


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _state_key(state: str) -> str:
    return f"webmail:oauth-state:{hash_token(state)}"


def begin_oauth(provider: str, mailbox_id: str, return_to: str = "/webmail/accounts") -> dict[str, str]:
    config = provider_config(provider)
    if not config.configured:
        raise MailOAuthError(f"{config.name} OAuth is not configured on this Ithute Mail installation")

    state = secrets.token_urlsafe(40)
    nonce = secrets.token_urlsafe(32)
    payload = {
        "provider": config.key,
        "mailbox_id": mailbox_id,
        "return_to": return_to if return_to.startswith("/webmail") else "/webmail/accounts",
        "nonce": nonce,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _redis().setex(_state_key(state), 600, json.dumps(payload, separators=(",", ":")))
    except redis.RedisError as exc:
        raise MailOAuthError("OAuth state store is unavailable") from exc

    params: dict[str, str] = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.scopes),
        "state": state,
        "nonce": nonce,
    }
    if config.key == "google":
        params.update({"access_type": "offline", "prompt": "consent", "include_granted_scopes": "true"})
    else:
        params.update({"response_mode": "query", "prompt": "select_account"})
    return {"authorization_url": f"{config.authorize_url}?{urlencode(params)}", "state": state}


def consume_state(state: str) -> dict[str, Any]:
    if not state:
        raise MailOAuthError("OAuth state is missing")
    key = _state_key(state)
    try:
        pipe = _redis().pipeline()
        pipe.get(key)
        pipe.delete(key)
        raw, _ = pipe.execute()
    except redis.RedisError as exc:
        raise MailOAuthError("OAuth state store is unavailable") from exc
    if not raw:
        raise MailOAuthError("OAuth request expired or was already used")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MailOAuthError("OAuth request state is invalid") from exc
    if not isinstance(payload, dict) or not payload.get("mailbox_id") or not payload.get("provider"):
        raise MailOAuthError("OAuth request state is invalid")
    return payload


def _decode_direct_token_claims(id_token: str) -> dict[str, Any]:
    """Decode identity claims returned directly by the trusted token endpoint.

    The token itself arrives over the authenticated TLS exchange with the OAuth
    provider. We do not accept an id_token from the browser or query string.
    Signature verification can be added later without changing this boundary.
    """
    if not id_token:
        return {}
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False, "verify_aud": False})
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def exchange_code(provider: str, code: str) -> dict[str, Any]:
    config = provider_config(provider)
    if not config.configured:
        raise MailOAuthError(f"{config.name} OAuth is not configured")
    if not code:
        raise MailOAuthError("OAuth authorization code is missing")

    try:
        response = httpx.post(
            config.token_url,
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code": code,
                "redirect_uri": config.redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=min(float(settings.external_provider_timeout_seconds), 30.0),
        )
    except httpx.HTTPError as exc:
        raise MailOAuthError(f"Unable to contact {config.name} OAuth service") from exc
    if response.status_code >= 400:
        raise MailOAuthError(f"{config.name} rejected the authorization exchange")
    try:
        data = response.json()
    except ValueError as exc:
        raise MailOAuthError(f"{config.name} returned an invalid OAuth response") from exc

    access_token = str(data.get("access_token") or "")
    refresh_token = str(data.get("refresh_token") or "")
    if not access_token:
        raise MailOAuthError(f"{config.name} did not return an access token")
    expires_in = max(60, int(data.get("expires_in") or 3600))
    claims = _decode_direct_token_claims(str(data.get("id_token") or ""))
    address = str(
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or ""
    ).strip().lower()

    if config.key == "google" and not address:
        try:
            userinfo = httpx.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=min(float(settings.external_provider_timeout_seconds), 30.0),
            )
            if userinfo.is_success:
                payload = userinfo.json()
                address = str(payload.get("email") or "").strip().lower()
                claims = {**claims, **payload}
        except (httpx.HTTPError, ValueError):
            pass
    if "@" not in address:
        raise MailOAuthError(f"{config.name} did not provide a usable mailbox address")

    return {
        "provider": config.key,
        "address": address,
        "display_name": str(claims.get("name") or "").strip()[:255],
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "scope": str(data.get("scope") or " ".join(config.scopes)).split(),
        "imap_host": config.imap_host,
        "imap_port": 993,
        "imap_security": "ssl",
        "smtp_host": config.smtp_host,
        "smtp_port": 587,
        "smtp_security": "starttls",
    }


def refresh_access_token(provider: str, refresh_token: str) -> dict[str, Any]:
    config = provider_config(provider)
    if not config.configured or not refresh_token:
        raise MailOAuthError("OAuth refresh is not available for this account")
    data = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    if config.key == "microsoft":
        data["scope"] = " ".join(config.scopes)
    try:
        response = httpx.post(
            config.token_url,
            data=data,
            timeout=min(float(settings.external_provider_timeout_seconds), 30.0),
        )
    except httpx.HTTPError as exc:
        raise MailOAuthError(f"Unable to refresh {config.name} authorization") from exc
    if response.status_code >= 400:
        raise MailOAuthError(f"{config.name} authorization needs to be renewed")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MailOAuthError(f"{config.name} returned an invalid refresh response") from exc
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise MailOAuthError(f"{config.name} did not return a refreshed access token")
    expires_in = max(60, int(payload.get("expires_in") or 3600))
    return {
        "access_token": access_token,
        "refresh_token": str(payload.get("refresh_token") or refresh_token),
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "scope": str(payload.get("scope") or "").split(),
    }


def xoauth2_bytes(username: str, access_token: str) -> bytes:
    return f"user={username}\x01auth=Bearer {access_token}\x01\x01".encode("utf-8")


def xoauth2_smtp_value(username: str, access_token: str) -> str:
    return base64.b64encode(xoauth2_bytes(username, access_token)).decode("ascii")
