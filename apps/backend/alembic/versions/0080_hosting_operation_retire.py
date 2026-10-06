"""allow retire hosting project operations

Revision ID: 0080_hosting_operation_retire
Revises: 0079_failure_domains
"""

from alembic import op

revision = "0080_hosting_operation_retire"
down_revision = "0079_failure_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_hosting_project_operation_kind",
        "hosting_project_operations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_hosting_project_operation_kind",
        "hosting_project_operations",
        "operation IN ('restart','logs','retire')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_hosting_project_operation_kind",
        "hosting_project_operations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_hosting_project_operation_kind",
        "hosting_project_operations",
        "operation IN ('restart','logs')",
    )
