"""create roles table

Revision ID: 2aeb7f96e160
Revises: 4c6895146d49
Create Date: 2026-04-28
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers
revision: str = "2aeb7f96e160"
down_revision: Union[str, Sequence[str], None] = "4c6895146d49"
branch_labels = None
depends_on = None


# IMPORTANT:
# Use PostgreSQL ENUM directly
# create_type=False prevents recreation

role_enum = postgresql.ENUM(
    "super_admin",
    "school_admin",
    "teacher",
    "student",
    "parent",
    name="userrole",
    create_type=False
)


def upgrade() -> None:
    """Upgrade schema"""

    op.create_table(
        "roles",

        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False
        ),

        sa.Column(
            "name",
            role_enum,
            nullable=False
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False
        ),

        sa.Column(
            "created_by",
            sa.String(length=36),
            nullable=True
        ),

        sa.Column(
            "updated_by",
            sa.String(length=36),
            nullable=True
        ),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Seed default roles

    roles_table = sa.table(
        "roles",
        sa.column("id", postgresql.UUID),
        sa.column("name", role_enum),
    )

    op.bulk_insert(
        roles_table,
        [
            {
                "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
                "name": "super_admin",
            },
            {
                "id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
                "name": "school_admin",
            },
            {
                "id": uuid.UUID("33333333-3333-3333-3333-333333333333"),
                "name": "teacher",
            },
            {
                "id": uuid.UUID("44444444-4444-4444-4444-444444444444"),
                "name": "student",
            },
            {
                "id": uuid.UUID("55555555-5555-5555-5555-555555555555"),
                "name": "parent",
            },
        ]
    )


def downgrade() -> None:
    """Downgrade schema"""

    op.drop_table("roles")