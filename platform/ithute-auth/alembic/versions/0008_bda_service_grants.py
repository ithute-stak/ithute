"""grant Business Digital Address scopes to simulator clients

Revision ID: 0008_bda_service_grants
Revises: 0007_identity_invites
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

from alembic import op
import sqlalchemy as sa


revision = "0008_bda_service_grants"
down_revision = "0007_identity_invites"
branch_labels = None
depends_on = None


_GRANTS: dict[str, dict[str, str]] = {
    "trade-simulator": {
        "audience": "business-digital-address",
        "scope": "business.register",
    },
    "rsl-simulator": {
        "audience": "business-digital-address",
        "scope": "official-message.send",
    },
}


def _decode_list(raw: str | None) -> list[str]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        parsed = []
    if not isinstance(parsed, list):
        return []
    return [value for value in parsed if isinstance(value, str) and value]


def _encode(values: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(values)), separators=(",", ":"))


def _apply(*, add: bool) -> None:
    connection = op.get_bind()
    table = sa.table(
        "managed_service_clients",
        sa.column("client_id", sa.String()),
        sa.column("allowed_audiences_json", sa.Text()),
        sa.column("allowed_scopes_json", sa.Text()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    for client_id, grant in _GRANTS.items():
        row = connection.execute(
            sa.select(
                table.c.allowed_audiences_json,
                table.c.allowed_scopes_json,
            ).where(table.c.client_id == client_id)
        ).mappings().first()
        if row is None:
            raise RuntimeError(f"required managed service client is missing: {client_id}")

        audiences = _decode_list(row["allowed_audiences_json"])
        scopes = _decode_list(row["allowed_scopes_json"])
        if add:
            if grant["audience"] not in audiences:
                audiences.append(grant["audience"])
            if grant["scope"] not in scopes:
                scopes.append(grant["scope"])
        else:
            audiences = [value for value in audiences if value != grant["audience"]]
            scopes = [value for value in scopes if value != grant["scope"]]

        connection.execute(
            table.update()
            .where(table.c.client_id == client_id)
            .values(
                allowed_audiences_json=_encode(audiences),
                allowed_scopes_json=_encode(scopes),
                updated_at=now,
            )
        )


def upgrade() -> None:
    _apply(add=True)


def downgrade() -> None:
    _apply(add=False)
