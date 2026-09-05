import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import jwt
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import service_account
from pywebpush import WebPushException, webpush

from .config import Settings


class ProviderNotConfigured(RuntimeError):
    pass


class InvalidEndpointError(RuntimeError):
    """The provider endpoint/token is no longer valid and may be deactivated."""


class PermanentProviderError(RuntimeError):
    """The individual message cannot be delivered; keep the endpoint active."""


class RetryableProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderResult:
    provider_message_id: str | None = None


def _payload(message, delivery_id: str | None = None) -> dict:
    data = json.loads(message.data_json or "{}")
    if message.route:
        data.setdefault("route", message.route)
    data.setdefault("ithute_message_id", str(message.id))
    if delivery_id:
        data.setdefault("ithute_delivery_id", delivery_id)
    return data


def _string_data(data: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[str(key)] = value
        else:
            result[str(key)] = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return result


def _ttl_seconds(message) -> int:
    remaining = (message.expires_at - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(remaining))


def _fcm_error(response: httpx.Response) -> tuple[str, set[str]]:
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        return "", set()
    status = str(error.get("status") or "").upper()
    codes: set[str] = set()
    for detail in error.get("details") or []:
        if isinstance(detail, dict):
            code = detail.get("errorCode")
            if code:
                codes.add(str(code).upper())
    return status, codes


def send_fcm(settings: Settings, token: str, message, delivery_id: str | None = None) -> ProviderResult:
    if not settings.fcm_project_id:
        raise ProviderNotConfigured("FCM project is not configured")
    try:
        credentials = service_account.Credentials.from_service_account_file(
            settings.fcm_credentials_file,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
    except FileNotFoundError as exc:
        raise ProviderNotConfigured("FCM credential file is missing") from exc
    except Exception as exc:
        raise ProviderNotConfigured("FCM service-account credentials are invalid") from exc
    try:
        credentials.refresh(GoogleRequest())
    except Exception as exc:
        raise RetryableProviderError("FCM credential refresh failed") from exc

    ttl = _ttl_seconds(message)
    if ttl <= 0:
        raise PermanentProviderError("notification expired before FCM delivery")

    payload = {
        "message": {
            "token": token,
            "notification": {"title": message.title, "body": message.body},
            "data": _string_data(_payload(message, delivery_id)),
            "android": {
                "priority": "HIGH",
                "ttl": f"{ttl}s",
                "notification": {
                    "sound": message.sound or "default",
                    "channel_id": settings.fcm_android_channel_id,
                },
            },
        }
    }
    try:
        response = httpx.post(
            f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send",
            headers={"Authorization": f"Bearer {credentials.token}"},
            json=payload,
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise RetryableProviderError("FCM network request failed") from exc

    status, codes = _fcm_error(response)
    if "UNREGISTERED" in codes or status == "UNREGISTERED" or response.status_code == 410:
        raise InvalidEndpointError("FCM registration token is no longer registered")
    if status == "NOT_FOUND":
        raise ProviderNotConfigured("FCM project or messaging resource was not found")
    if "SENDER_ID_MISMATCH" in codes or "THIRD_PARTY_AUTH_ERROR" in codes or status in {
        "PERMISSION_DENIED",
        "UNAUTHENTICATED",
    }:
        raise ProviderNotConfigured(f"FCM project credentials rejected the request ({status or response.status_code})")
    if response.status_code == 429 or response.status_code >= 500 or status in {
        "RESOURCE_EXHAUSTED",
        "UNAVAILABLE",
        "INTERNAL",
    }:
        raise RetryableProviderError(f"FCM temporary error {status or response.status_code}")
    if response.is_error:
        raise PermanentProviderError(f"FCM rejected message: {status or response.status_code}")
    body = response.json()
    return ProviderResult(provider_message_id=body.get("name"))


def send_apns(settings: Settings, token: str, message, delivery_id: str | None = None) -> ProviderResult:
    required = [settings.apns_team_id, settings.apns_key_id, settings.apns_bundle_id]
    if not all(required):
        raise ProviderNotConfigured("APNs identity is not configured")
    try:
        private_key = settings.read_secret_file(settings.apns_private_key_file)
    except FileNotFoundError as exc:
        raise ProviderNotConfigured("APNs private key is missing") from exc
    provider_token = jwt.encode(
        {"iss": settings.apns_team_id, "iat": int(time.time())},
        private_key,
        algorithm="ES256",
        headers={"kid": settings.apns_key_id},
    )
    host = "https://api.sandbox.push.apple.com" if settings.apns_use_sandbox else "https://api.push.apple.com"
    ttl = _ttl_seconds(message)
    if ttl <= 0:
        raise PermanentProviderError("notification expired before APNs delivery")
    payload = {
        "aps": {
            "alert": {"title": message.title, "body": message.body},
            "sound": message.sound or "default",
        },
        "data": _payload(message, delivery_id),
    }
    try:
        with httpx.Client(http2=True, timeout=15) as client:
            response = client.post(
                f"{host}/3/device/{token}",
                headers={
                    "authorization": f"bearer {provider_token}",
                    "apns-topic": settings.apns_bundle_id or "",
                    "apns-push-type": "alert",
                    "apns-priority": "10",
                    "apns-expiration": str(int(time.time()) + ttl),
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise RetryableProviderError("APNs network request failed") from exc

    reason = ""
    try:
        reason = str(response.json().get("reason") or "")
    except ValueError:
        pass
    if response.status_code == 410 or reason in {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"}:
        raise InvalidEndpointError(f"APNs endpoint is invalid: {reason or response.status_code}")
    if response.status_code in {403} or reason in {"ExpiredProviderToken", "InvalidProviderToken", "MissingProviderToken"}:
        raise ProviderNotConfigured(f"APNs provider authentication failed: {reason or response.status_code}")
    if response.status_code == 429 or response.status_code >= 500:
        raise RetryableProviderError(f"APNs temporary error {response.status_code}")
    if response.is_error:
        raise PermanentProviderError(f"APNs rejected message: {reason or response.status_code}")
    return ProviderResult(provider_message_id=response.headers.get("apns-id"))


def send_webpush(settings: Settings, subscription_json: str, message, delivery_id: str | None = None) -> ProviderResult:
    if not settings.vapid_public_key:
        raise ProviderNotConfigured("Web Push VAPID is not configured")
    try:
        private_key = settings.read_secret_file(settings.vapid_private_key_file)
    except FileNotFoundError as exc:
        raise ProviderNotConfigured("VAPID private key is missing") from exc
    try:
        subscription = json.loads(subscription_json)
        webpush(
            subscription_info=subscription,
            data=json.dumps(
                {
                    "title": message.title,
                    "body": message.body,
                    "route": message.route,
                    "sound": message.sound,
                    "data": _payload(message, delivery_id),
                }
            ),
            vapid_private_key=private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=_ttl_seconds(message),
        )
    except ValueError as exc:
        raise InvalidEndpointError("Web Push subscription is invalid") from exc
    except WebPushException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {404, 410}:
            raise InvalidEndpointError("Web Push subscription is no longer registered") from exc
        if status_code == 429 or (status_code is not None and status_code >= 500):
            raise RetryableProviderError(f"Web Push temporary error {status_code}") from exc
        raise PermanentProviderError("Web Push delivery was rejected") from exc
    return ProviderResult()


def deliver(
    settings: Settings,
    provider: str,
    endpoint: str,
    message,
    delivery_id: str | None = None,
) -> ProviderResult:
    if provider == "fcm":
        return send_fcm(settings, endpoint, message, delivery_id)
    if provider == "apns":
        return send_apns(settings, endpoint, message, delivery_id)
    if provider == "webpush":
        return send_webpush(settings, endpoint, message, delivery_id)
    raise PermanentProviderError(f"unsupported provider {provider}")
