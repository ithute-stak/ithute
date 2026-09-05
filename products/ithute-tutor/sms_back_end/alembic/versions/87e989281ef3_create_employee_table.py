"""create employee table

Revision ID: 87e989281ef3
Revises: f37b95f70306
Create Date: 2026-05-17 13:01:54.397751
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '87e989281ef3'
down_revision: Union[str, Sequence[str], None] = 'f37b95f70306'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # =====================================================
    # CREATE EMPLOYEES TABLE
    # =====================================================
    op.create_table(
        'employees',

        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            nullable=False
        ),

        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False
        ),

        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False
        ),

        sa.Column(
            'created_by',
            sa.String(length=36),
            nullable=True
        ),

        sa.Column(
            'updated_by',
            sa.String(length=36),
            nullable=True
        ),

        sa.PrimaryKeyConstraint('id')
    )

    # =====================================================
    # DROP OLD FK FIRST
    # =====================================================
    op.drop_constraint(
        op.f('teachers_id_fkey'),
        'teachers',
        type_='foreignkey'
    )

    # =====================================================
    # CONVERT employee_id -> UUID
    # =====================================================
    op.alter_column(
        'teachers',
        'employee_id',

        existing_type=sa.VARCHAR(length=255),

        type_=postgresql.UUID(as_uuid=True),

        existing_nullable=False,

        postgresql_using='employee_id::uuid'
    )

    # =====================================================
    # CREATE NEW FK
    # =====================================================
    op.create_foreign_key(
        'fk_teachers_employee_id',

        'teachers',

        'employees',

        ['employee_id'],

        ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""

    # =====================================================
    # DROP NEW FK
    # =====================================================
    op.drop_constraint(
        'fk_teachers_employee_id',
        'teachers',
        type_='foreignkey'
    )

    # =====================================================
    # CONVERT UUID BACK TO VARCHAR
    # =====================================================
    op.alter_column(
        'teachers',
        'employee_id',

        existing_type=postgresql.UUID(as_uuid=True),

        type_=sa.VARCHAR(length=255),

        existing_nullable=False,

        postgresql_using='employee_id::text'
    )

    # =====================================================
    # RESTORE OLD FK
    # =====================================================
    op.create_foreign_key(
        op.f('teachers_id_fkey'),

        'teachers',

        'users',

        ['id'],

        ['id']
    )

    # =====================================================
    # DROP EMPLOYEES TABLE
    # =====================================================
    op.drop_table('employees')