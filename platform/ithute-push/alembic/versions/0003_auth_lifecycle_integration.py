"""integrate Push with Auth session lifecycle

Revision ID: 0003_auth_lifecycle_integration
Revises: 0002_push_reliability
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_auth_lifecycle_integration"
down_revision = "0002_push_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("push_endpoints", sa.Column("auth_session_id", sa.Uuid(), nullable=True))
    op.create_index("ix_push_endpoints_auth_session_id", "push_endpoints", ["auth_session_id"])
    op.execute("UPDATE push_endpoints SET active = false")

    op.create_table(
        "auth_lifecycle_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("auth_user_id", sa.Uuid(), nullable=True),
        sa.Column("auth_session_id", sa.Uuid(), nullable=True),
        sa.Column("application_id", sa.String(length=120), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_auth_lifecycle_events_event_type", "auth_lifecycle_events", ["event_type"])
    op.create_index("ix_auth_lifecycle_events_auth_user_id", "auth_lifecycle_events", ["auth_user_id"])
    op.create_index("ix_auth_lifecycle_events_auth_session_id", "auth_lifecycle_events", ["auth_session_id"])
    op.create_index("ix_auth_lifecycle_events_application_id", "auth_lifecycle_events", ["application_id"])

    op.create_table(
        "revoked_auth_sessions",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("auth_user_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.String(length=120), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index("ix_revoked_auth_sessions_auth_user_id", "revoked_auth_sessions", ["auth_user_id"])
    op.create_index("ix_revoked_auth_sessions_application_id", "revoked_auth_sessions", ["application_id"])

    op.create_table(
        "auth_user_states",
        sa.Column("auth_user_id", sa.Uuid(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("auth_user_id"),
    )

    op.create_table(
        "application_states",
        sa.Column("application_id", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("application_id"),
    )


def downgrade() -> None:
    op.drop_table("application_states")
    op.drop_table("auth_user_states")
    op.drop_table("revoked_auth_sessions")
    op.drop_table("auth_lifecycle_events")
    op.drop_index("ix_push_endpoints_auth_session_id", table_name="push_endpoints")
    op.drop_column("push_endpoints", "auth_session_id")
