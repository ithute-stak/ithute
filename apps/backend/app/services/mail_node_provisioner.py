from __future__ import annotations

import httpx

from app.core.config import settings
from app.services.secret_provider import resolve_secret


class MailNodeProvisionerError(RuntimeError):
    pass


def provisioner_configured() -> bool:
    return bool(
        settings.mail_node_provisioner_url
        and (settings.mail_node_provisioner_token_ref or settings.mail_node_provisioner_token)
    )


def provision_mail_node(payload: dict) -> dict:
    if not provisioner_configured():
        raise MailNodeProvisionerError("Mail node provisioner is not configured")
    try:
        response = httpx.post(
            settings.mail_node_provisioner_url or "",
            json=payload,
            headers={
                "Authorization": "Bearer " + resolve_secret(
                    settings.mail_node_provisioner_token_ref,
                    settings.mail_node_provisioner_token,
                    name="mail node provisioner token",
                ),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=settings.mail_node_provisioner_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MailNodeProvisionerError(f"Mail node provisioner request failed: {exc}") from exc

    required = ("provider", "instance_id", "hostname")
    missing = [key for key in required if not str(body.get(key) or "").strip()]
    if missing:
        raise MailNodeProvisionerError(f"Provisioner response is missing required fields: {', '.join(missing)}")
    return {
        "provider": str(body["provider"]).strip(),
        "instance_id": str(body["instance_id"]).strip(),
        "hostname": str(body["hostname"]).strip().lower().rstrip("."),
        "public_ip": str(body.get("public_ip") or "").strip() or None,
        "ssh_user": str(body.get("ssh_user") or "").strip() or None,
        "ssh_port": int(body.get("ssh_port") or 22),
        "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
    }
