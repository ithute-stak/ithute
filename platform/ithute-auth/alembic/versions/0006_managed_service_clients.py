"""add managed platform service clients

Revision ID: 0006_managed_service_clients
Revises: 0005_push_event_outbox
"""

from datetime import datetime, timezone
import json
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0006_managed_service_clients"
down_revision = "0005_push_event_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_service_clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("allowed_audiences_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allowed_scopes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index("ix_managed_service_clients_client_id", "managed_service_clients", ["client_id"], unique=True)
    op.create_index("ix_managed_service_clients_expires_at", "managed_service_clients", ["expires_at"])

    op.create_table(
        "managed_service_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_client_id", sa.Uuid(), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("secret_prefix", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["service_client_id"], ["managed_service_clients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secret_hash"),
    )
    op.create_index(
        "ix_managed_service_credentials_service_client_id",
        "managed_service_credentials",
        ["service_client_id"],
    )
    op.create_index(
        "ix_managed_service_credentials_secret_hash",
        "managed_service_credentials",
        ["secret_hash"],
        unique=True,
    )
    op.create_index("ix_managed_service_credentials_expires_at", "managed_service_credentials", ["expires_at"])
    op.create_index("ix_managed_service_credentials_revoked_at", "managed_service_credentials", ["revoked_at"])

    now = datetime.now(timezone.utc)
    service_clients = sa.table(
        "managed_service_clients",
        sa.column("id", sa.Uuid()),
        sa.column("client_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("allowed_audiences_json", sa.Text()),
        sa.column("allowed_scopes_json", sa.Text()),
        sa.column("is_active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        service_clients,
        [
            {
                "id": uuid.uuid4(),
                "client_id": "business-digital-address",
                "name": "Business Digital Address",
                "description": "Standalone business identity and official communications platform.",
                "allowed_audiences_json": json.dumps(
                    ["ithute-auth", "ithute-mail", "ithute-dns", "ithute-notification"],
                    separators=(",", ":"),
                ),
                "allowed_scopes_json": json.dumps(
                    ["identity.invite", "mailbox.create", "mail.send", "dns.verify", "notification.send"],
                    separators=(",", ":"),
                ),
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid.uuid4(),
                "client_id": "trade-simulator",
                "name": "Trade Simulator",
                "description": "Development client that simulates business-registration provisioning from Trade/OBFC.",
                "allowed_audiences_json": json.dumps(
                    ["ithute-auth", "ithute-mail", "ithute-notification"],
                    separators=(",", ":"),
                ),
                "allowed_scopes_json": json.dumps(
                    ["identity.invite", "mailbox.create", "notification.send"],
                    separators=(",", ":"),
                ),
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid.uuid4(),
                "client_id": "rsl-simulator",
                "name": "RSL Simulator",
                "description": "Development client that simulates authenticated RSL communications.",
                "allowed_audiences_json": json.dumps(
                    ["ithute-mail", "ithute-notification"],
                    separators=(",", ":"),
                ),
                "allowed_scopes_json": json.dumps(
                    ["mail.send", "notification.send"],
                    separators=(",", ":"),
                ),
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("managed_service_credentials")
    op.drop_table("managed_service_clients")
