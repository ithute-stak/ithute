from __future__ import annotations

import json
import secrets
from urllib.parse import urlparse
from typing import Any

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import settings
from app.models import PasskeyCredential, User

PASSKEY_FLOW_TTL_SECONDS = 300
PASSKEY_RP_NAME = "Ithute"


class PasskeyError(ValueError):
    pass


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def relying_party() -> tuple[str, str]:
    origin = str(settings.frontend_url or "").strip().rstrip("/")
    parsed = urlparse(origin)
    rp_id = (parsed.hostname or "").lower()
    if not origin or not rp_id or parsed.scheme not in {"http", "https"}:
        raise PasskeyError("Passkey relying-party configuration is invalid")
    if settings.environment.lower() == "production" and parsed.scheme != "https":
        raise PasskeyError("Passkeys require HTTPS in production")
    return rp_id, origin


def _store_flow(kind: str, payload: dict[str, Any]) -> str:
    flow_id = secrets.token_urlsafe(32)
    try:
        _redis().setex(
            f"ithute:passkey:{kind}:{flow_id}",
            PASSKEY_FLOW_TTL_SECONDS,
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
        )
    except redis.RedisError as exc:
        raise PasskeyError("Passkey challenge service is unavailable") from exc
    return flow_id


def _consume_flow(kind: str, flow_id: str) -> dict[str, Any]:
    if not flow_id or len(flow_id) > 256:
        raise PasskeyError("Passkey challenge is invalid or expired")
    key = f"ithute:passkey:{kind}:{flow_id}"
    try:
        client = _redis()
        pipe = client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        raw, _ = pipe.execute()
    except redis.RedisError as exc:
        raise PasskeyError("Passkey challenge service is unavailable") from exc
    if not raw:
        raise PasskeyError("Passkey challenge is invalid or expired")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PasskeyError("Passkey challenge is invalid or expired") from exc
    if not isinstance(payload, dict):
        raise PasskeyError("Passkey challenge is invalid or expired")
    return payload


def registration_options(db: Session, user: User) -> dict[str, Any]:
    rp_id, _origin = relying_party()
    existing = db.scalars(
        select(PasskeyCredential).where(
            PasskeyCredential.user_id == user.id,
            PasskeyCredential.revoked_at.is_(None),
        )
    ).all()
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name=PASSKEY_RP_NAME,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.full_name or user.email,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(item.credential_id))
            for item in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    flow_id = _store_flow(
        "register",
        {
            "user_id": str(user.id),
            "challenge": bytes_to_base64url(options.challenge),
        },
    )
    return {
        "flow_id": flow_id,
        "publicKey": json.loads(options_to_json(options)),
        "expires_in": PASSKEY_FLOW_TTL_SECONDS,
    }


def verify_registration(
    db: Session,
    *,
    user: User,
    flow_id: str,
    credential: dict[str, Any],
    name: str,
) -> PasskeyCredential:
    rp_id, origin = relying_party()
    flow = _consume_flow("register", flow_id)
    if str(flow.get("user_id") or "") != str(user.id):
        raise PasskeyError("Passkey challenge does not belong to this account")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(flow.get("challenge") or "")),
            expected_rp_id=rp_id,
            expected_origin=origin,
            require_user_verification=True,
        )
    except InvalidRegistrationResponse as exc:
        raise PasskeyError("Passkey registration could not be verified") from exc

    credential_id = bytes_to_base64url(verified.credential_id)
    if db.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id == credential_id)):
        raise PasskeyError("This passkey is already registered")

    response = credential.get("response") if isinstance(credential.get("response"), dict) else {}
    transports = response.get("transports") if isinstance(response.get("transports"), list) else []
    device_type = getattr(verified.credential_device_type, "value", str(verified.credential_device_type))
    item = PasskeyCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=int(verified.sign_count),
        name=(name.strip() or "Passkey")[:120],
        transports_json=json.dumps([str(value) for value in transports[:12]], separators=(",", ":")),
        device_type=str(device_type)[:40],
        backed_up=bool(verified.credential_backed_up),
    )
    db.add(item)
    db.flush()
    return item


def authentication_options() -> dict[str, Any]:
    rp_id, _origin = relying_party()
    options = generate_authentication_options(
        rp_id=rp_id,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    flow_id = _store_flow(
        "authenticate",
        {"challenge": bytes_to_base64url(options.challenge)},
    )
    return {
        "flow_id": flow_id,
        "publicKey": json.loads(options_to_json(options)),
        "expires_in": PASSKEY_FLOW_TTL_SECONDS,
    }


def verify_authentication(
    db: Session,
    *,
    flow_id: str,
    credential: dict[str, Any],
) -> tuple[User, PasskeyCredential]:
    rp_id, origin = relying_party()
    flow = _consume_flow("authenticate", flow_id)
    credential_id = str(credential.get("id") or "").strip()
    if not credential_id:
        raise PasskeyError("Passkey credential is missing")

    item = db.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.credential_id == credential_id,
            PasskeyCredential.revoked_at.is_(None),
        )
    )
    if item is None:
        raise PasskeyError("Passkey credential is not recognized")
    user = db.get(User, item.user_id)
    if user is None or not user.is_active:
        raise PasskeyError("Passkey account is unavailable")

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(flow.get("challenge") or "")),
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=item.public_key,
            credential_current_sign_count=item.sign_count,
            require_user_verification=True,
        )
    except InvalidAuthenticationResponse as exc:
        raise PasskeyError("Passkey authentication could not be verified") from exc

    item.sign_count = int(verified.new_sign_count)
    item.backed_up = bool(verified.credential_backed_up)
    item.device_type = str(getattr(verified.credential_device_type, "value", verified.credential_device_type))[:40]
    return user, item
