from __future__ import annotations

import hashlib
import logging

import httpx

from app.core.config import settings
from app.services.ithute_auth import get_ithute_auth_settings


logger = logging.getLogger(__name__)


def _source_ref(*, mailbox_address: str, message_ref: str, label: str) -> str:
    material = f"{mailbox_address.lower()}\n{message_ref}\n{label}".encode("utf-8")
    return "mail:" + hashlib.sha256(material).hexdigest()


def publish_verified_mail_risk(
    *,
    mailbox_address: str,
    message_ref: str,
    label: str,
    confidence: float,
) -> bool:
    if label not in {"phishing", "bec"} or confidence < 0.80:
        return False
    secret = (settings.security_intelligence_client_secret or "").strip()
    if not secret:
        logger.warning("Central identity risk publishing is not configured")
        return False

    auth = get_ithute_auth_settings()
    signal_type = "mail.phishing.verified" if label == "phishing" else "mail.bec.verified"
    timeout = settings.security_intelligence_timeout_seconds

    try:
        token_response = httpx.post(
            f"{auth.resolved_internal_url}/v1/auth/service-token",
            json={
                "client_id": settings.security_intelligence_client_id,
                "client_secret": secret,
                "audience": "ithute-auth",
                "scope": "security.risk.write",
            },
            timeout=timeout,
        )
        token_response.raise_for_status()
        token = str(token_response.json().get("access_token") or "")
        if not token:
            raise RuntimeError("central auth did not return a service token")

        response = httpx.post(
            f"{auth.resolved_internal_url}/v1/internal/security/risk-signals",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "subject_email": mailbox_address.lower(),
                "source_ref": _source_ref(
                    mailbox_address=mailbox_address,
                    message_ref=message_ref,
                    label=label,
                ),
                "signal_type": signal_type,
                "confidence": int(round(confidence * 100)),
                "verified_by_human": True,
                "metadata": {
                    "mailbox_domain": mailbox_address.rsplit("@", 1)[-1].lower() if "@" in mailbox_address else "",
                    "verdict": label,
                    "evidence_version": "mail-intelligence-v2",
                },
            },
            timeout=timeout,
        )
        response.raise_for_status()
        return bool(response.json().get("accepted"))
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        # Human verdict persistence remains authoritative even if the central
        # identity service is temporarily unavailable. A repeated identical
        # verdict is idempotent and can safely retry publication.
        logger.warning("Unable to publish verified mail risk to central identity: %s", exc)
        return False
