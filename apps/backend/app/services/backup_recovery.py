import httpx

from app.core.config import settings
from app.services.secret_provider import resolve_secret


class RecoveryServiceError(RuntimeError):
    pass


def recover_mailbox(mailbox_address: str, snapshot_id: str | None = None) -> dict:
    payload = {"mailbox_address": mailbox_address, "snapshot_id": snapshot_id}
    try:
        response = httpx.post(
            f"{settings.recovery_ops_url.rstrip('/')}/recover",
            json=payload,
            headers={
                "Authorization": "Bearer " + resolve_secret(
                    settings.recovery_ops_token_ref,
                    settings.recovery_ops_token,
                    name="recovery operations token",
                )
            },
            timeout=settings.recovery_ops_timeout_seconds,
        )
        if response.status_code >= 400:
            raise RecoveryServiceError(response.text[:500])
        return response.json()
    except httpx.HTTPError as exc:
        raise RecoveryServiceError(f"Recovery service unavailable: {exc}") from exc
