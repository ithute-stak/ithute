import httpx

from app.core.config import settings


class RecoveryServiceError(RuntimeError):
    pass


def recover_mailbox(mailbox_address: str, snapshot_id: str | None = None) -> dict:
    payload = {"mailbox_address": mailbox_address, "snapshot_id": snapshot_id}
    try:
        response = httpx.post(
            f"{settings.recovery_ops_url.rstrip('/')}/recover",
            json=payload,
            headers={"Authorization": f"Bearer {settings.recovery_ops_token}"},
            timeout=settings.recovery_ops_timeout_seconds,
        )
        if response.status_code >= 400:
            raise RecoveryServiceError(response.text[:500])
        return response.json()
    except httpx.HTTPError as exc:
        raise RecoveryServiceError(f"Recovery service unavailable: {exc}") from exc
