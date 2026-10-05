"""allow multiple push transports per device

Revision ID: 0004_multi_transport_endpoints
Revises: 0003_auth_lifecycle_integration
"""

from alembic import op


revision = "0004_multi_transport_endpoints"
down_revision = "0003_auth_lifecycle_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_push_endpoint_identity", "push_endpoints", type_="unique")
    op.create_unique_constraint(
        "uq_push_endpoint_transport",
        "push_endpoints",
        ["auth_user_id", "application_id", "device_key", "provider"],
    )


def downgrade() -> None:
    # A downgrade is only safe when each device has at most one transport.
    op.drop_constraint("uq_push_endpoint_transport", "push_endpoints", type_="unique")
    op.create_unique_constraint(
        "uq_push_endpoint_identity",
        "push_endpoints",
        ["auth_user_id", "application_id", "device_key"],
    )
