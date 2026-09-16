"""grant BDA managed inbound mail forwarding

Revision ID: 0009_bda_mail_forward
Revises: 0008_bda_service_grants
"""

import json

from alembic import op
import sqlalchemy as sa


revision = "0009_bda_mail_forward"
down_revision = "0008_bda_service_grants"
branch_labels = None
depends_on = None


_CLIENT_ID = "business-digital-address"
_SCOPE = "mail.forward"


def _scopes(connection) -> list[str] | None:
    raw = connection.execute(
        sa.text(
            "SELECT allowed_scopes_json FROM managed_service_clients "
            "WHERE client_id = :client_id"
        ),
        {"client_id": _CLIENT_ID},
    ).scalar_one_or_none()
    if raw is None:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise RuntimeError("Business Digital Address managed-service scopes are invalid")
    return list(dict.fromkeys(parsed))


def _write(connection, scopes: list[str]) -> None:
    connection.execute(
        sa.text(
            "UPDATE managed_service_clients "
            "SET allowed_scopes_json = :scopes, updated_at = CURRENT_TIMESTAMP "
            "WHERE client_id = :client_id"
        ),
        {
            "client_id": _CLIENT_ID,
            "scopes": json.dumps(scopes, separators=(",", ":")),
        },
    )


def upgrade() -> None:
    connection = op.get_bind()
    scopes = _scopes(connection)
    if scopes is None:
        raise RuntimeError("Business Digital Address managed service client is missing")
    if _SCOPE not in scopes:
        scopes.append(_SCOPE)
        _write(connection, scopes)


def downgrade() -> None:
    connection = op.get_bind()
    scopes = _scopes(connection)
    if scopes is None:
        return
    if _SCOPE in scopes:
        _write(connection, [scope for scope in scopes if scope != _SCOPE])
