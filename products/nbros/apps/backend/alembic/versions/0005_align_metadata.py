"""Align uniqueness/index metadata with the current SQLAlchemy models.

Revision ID: 0005_align_metadata
Revises: 0004_fleet_inventory
"""
from alembic import op

revision = "0005_align_metadata"
down_revision = "0004_fleet_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These fields have always been unique. SQLAlchemy models declare them as
    # indexed unique columns, so align PostgreSQL with that representation.
    op.drop_constraint("branches_code_key", "branches", type_="unique")
    op.drop_index("ix_branches_code", table_name="branches")
    op.create_index("ix_branches_code", "branches", ["code"], unique=True)

    op.drop_constraint("uq_profiles_auth_user_id", "profiles", type_="unique")
    op.create_index("ix_profiles_auth_user_id", "profiles", ["auth_user_id"], unique=True)

    op.drop_constraint("vehicles_registration_plate_key", "vehicles", type_="unique")
    op.drop_index("ix_vehicles_registration_plate", table_name="vehicles")
    op.create_index(
        "ix_vehicles_registration_plate",
        "vehicles",
        ["registration_plate"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_vehicles_registration_plate", table_name="vehicles")
    op.create_index(
        "ix_vehicles_registration_plate",
        "vehicles",
        ["registration_plate"],
        unique=False,
    )
    op.create_unique_constraint(
        "vehicles_registration_plate_key", "vehicles", ["registration_plate"]
    )

    op.drop_index("ix_profiles_auth_user_id", table_name="profiles")
    op.create_unique_constraint("uq_profiles_auth_user_id", "profiles", ["auth_user_id"])

    op.drop_index("ix_branches_code", table_name="branches")
    op.create_index("ix_branches_code", "branches", ["code"], unique=False)
    op.create_unique_constraint("branches_code_key", "branches", ["code"])
