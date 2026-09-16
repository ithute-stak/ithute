"""add trusted identity invitations

Revision ID: 0007_trusted_identity_invitations
Revises: 0006_managed_service_clients
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_trusted_identity_invitations"
down_revision = "0006_managed_service_clients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_client_id", sa.String(length=120), nullable=False),
        sa.Column("external_reference", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("preferred_channel", sa.String(length=16), nullable=False),
        sa.Column("challenge_token_hash", sa.String(length=64), nullable=False),
        sa.Column("challenge_code_hash", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("delivery_status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("activation_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_client_id", "external_reference", name="uq_identity_invitation_source_reference"),
        sa.UniqueConstraint("challenge_token_hash"),
    )
    op.create_index("ix_identity_invitations_source_client_id", "identity_invitations", ["source_client_id"])
    op.create_index("ix_identity_invitations_external_reference", "identity_invitations", ["external_reference"])
    op.create_index("ix_identity_invitations_email", "identity_invitations", ["email"])
    op.create_index("ix_identity_invitations_phone", "identity_invitations", ["phone"])
    op.create_index("ix_identity_invitations_status", "identity_invitations", ["status"])
    op.create_index("ix_identity_invitations_expires_at", "identity_invitations", ["expires_at"])
    op.create_index("ix_identity_invitations_user_id", "identity_invitations", ["user_id"])


def downgrade() -> None:
    op.drop_table("identity_invitations")
