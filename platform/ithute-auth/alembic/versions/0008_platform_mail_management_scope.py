"""grant platform mailbox management scope

Revision ID: 0008_platform_mail_management_scope
Revises: 0007_trusted_identity_invitations
"""

import json

from alembic import op
import sqlalchemy as sa

revision = "0008_platform_mail_management_scope"
down_revision = "0007_trusted_identity_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT client_id, allowed_scopes_json FROM managed_service_clients WHERE client_id = :client_id"),
        {"client_id": "business-digital-address"},
    ).mappings().all()
    for row in rows:
        scopes = json.loads(row["allowed_scopes_json"] or "[]")
        if "mailbox.manage" not in scopes:
            scopes.append("mailbox.manage")
        connection.execute(
            sa.text("UPDATE managed_service_clients SET allowed_scopes_json = :scopes WHERE client_id = :client_id"),
            {"scopes": json.dumps(scopes, separators=(",", ":")), "client_id": row["client_id"]},
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT client_id, allowed_scopes_json FROM managed_service_clients WHERE client_id = :client_id"),
        {"client_id": "business-digital-address"},
    ).mappings().all()
    for row in rows:
        scopes = [scope for scope in json.loads(row["allowed_scopes_json"] or "[]") if scope != "mailbox.manage"]
        connection.execute(
            sa.text("UPDATE managed_service_clients SET allowed_scopes_json = :scopes WHERE client_id = :client_id"),
            {"scopes": json.dumps(scopes, separators=(",", ":")), "client_id": row["client_id"]},
        )
