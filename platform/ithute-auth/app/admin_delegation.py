import uuid
from datetime import timedelta

from .config import Settings
from .security import _encode, utcnow


PUSH_ADMIN_CLIENT_ID = "mailbox-dns"
PUSH_ADMIN_TOKEN_MINUTES = 2


def create_push_admin_token(
    *,
    settings: Settings,
    user_id: uuid.UUID,
    client_id: str,
    session_id: uuid.UUID,
) -> str:
    """Mint a short-lived human-bound token for Push administration.

    This token is intentionally different from product access, device, send and
    lifecycle tokens. Only the Mailbox DNS platform console may request it, and
    Push still validates the central human subject and Auth session id.
    """
    if client_id != PUSH_ADMIN_CLIENT_ID:
        raise ValueError("client is not approved for Push administration")
    issued_at = utcnow()
    return _encode(
        settings,
        {
            "iss": settings.issuer.rstrip("/"),
            "sub": str(user_id),
            "aud": "ithute-push",
            "azp": client_id,
            "sid": str(session_id),
            "scope": "push.admin",
            "token_use": "push_admin",
            "jti": str(uuid.uuid4()),
            "iat": int(issued_at.timestamp()),
            "nbf": int(issued_at.timestamp()),
            "exp": int((issued_at + timedelta(minutes=PUSH_ADMIN_TOKEN_MINUTES)).timestamp()),
        },
    )
