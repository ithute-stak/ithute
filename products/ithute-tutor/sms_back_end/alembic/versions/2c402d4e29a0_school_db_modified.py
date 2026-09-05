"""school db modified

Revision ID: 2c402d4e29a0
Revises: 2aeb7f96e160
Create Date: 2026-04-28 07:40:49.639030
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "2c402d4e29a0"
down_revision: Union[str, Sequence[str], None] = "2aeb7f96e160"
branch_labels = None
depends_on = None


# -------------------------
# CREATE ENUM FIRST
# -------------------------

school_category_enum = sa.Enum(
    "pre_school",
    "junior_school",
    "primary_school",
    "basic_education_school",
    "secondary_school",
    "high_school",
    "junior_college",
    "learning_center",
    name="schoolcategory"
)


def upgrade() -> None:
    """
    Upgrade schema.
    """

    # IMPORTANT: create enum first
    school_category_enum.create(op.get_bind(), checkfirst=True)

    # --------------------------------
    # SUBTABLES
    # --------------------------------

    op.create_table(
        "school_contact_persons",
        sa.Column("school_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("designation", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=False),

        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),

        sa.ForeignKeyConstraint(["school_id"], ["schools.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id"),
    )

    op.create_table(
        "school_proprietors",
        sa.Column("school_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("national_id", sa.String(length=100), nullable=True),
        sa.Column("phone", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=False),

        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),

        sa.ForeignKeyConstraint(["school_id"], ["schools.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("school_id"),
    )

    # --------------------------------
    # ADD SCHOOL COLUMNS
    # --------------------------------

    op.add_column("schools", sa.Column("school_code", sa.String(100), nullable=True))
    op.add_column("schools", sa.Column("registration_number", sa.String(100), nullable=True))
    op.add_column("schools", sa.Column("website", sa.String(255), nullable=True))

    op.add_column(
        "schools",
        sa.Column(
            "category",
            school_category_enum,
            nullable=False,
            server_default="primary_school"
        )
    )

    op.add_column("schools", sa.Column("is_registered", sa.Boolean(), nullable=True))
    op.add_column("schools", sa.Column("certificate_number", sa.String(255), nullable=True))
    op.add_column("schools", sa.Column("district", sa.String(255), nullable=False, server_default="Maseru"))
    op.add_column("schools", sa.Column("city", sa.String(255), nullable=True))
    op.add_column("schools", sa.Column("country", sa.String(100), nullable=True, server_default="Lesotho"))
    op.add_column("schools", sa.Column("land_ownership_type", sa.String(100), nullable=True))
    op.add_column("schools", sa.Column("title_deed_number", sa.String(255), nullable=True))
    op.add_column("schools", sa.Column("lease_agreement_reference", sa.String(255), nullable=True))
    op.add_column("schools", sa.Column("bank_name", sa.String(255), nullable=True))
    op.add_column("schools", sa.Column("account_name", sa.String(255), nullable=True))
    op.add_column("schools", sa.Column("financial_notes", sa.Text(), nullable=True))

    op.alter_column(
        "schools",
        "address",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.Text(),
        nullable=False
    )

    op.create_unique_constraint(
        "uq_schools_school_code",
        "schools",
        ["school_code"]
    )

    op.create_unique_constraint(
        "uq_schools_registration_number",
        "schools",
        ["registration_number"]
    )

    op.create_unique_constraint(
        "uq_schools_name",
        "schools",
        ["name"]
    )


def downgrade() -> None:
    """
    Downgrade schema.
    """

    op.drop_constraint("uq_schools_name", "schools", type_="unique")
    op.drop_constraint("uq_schools_registration_number", "schools", type_="unique")
    op.drop_constraint("uq_schools_school_code", "schools", type_="unique")

    op.alter_column(
        "schools",
        "address",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=255),
        nullable=True
    )

    op.drop_column("schools", "financial_notes")
    op.drop_column("schools", "account_name")
    op.drop_column("schools", "bank_name")
    op.drop_column("schools", "lease_agreement_reference")
    op.drop_column("schools", "title_deed_number")
    op.drop_column("schools", "land_ownership_type")
    op.drop_column("schools", "country")
    op.drop_column("schools", "city")
    op.drop_column("schools", "district")
    op.drop_column("schools", "certificate_number")
    op.drop_column("schools", "is_registered")
    op.drop_column("schools", "category")
    op.drop_column("schools", "website")
    op.drop_column("schools", "registration_number")
    op.drop_column("schools", "school_code")

    op.drop_table("school_proprietors")
    op.drop_table("school_contact_persons")

    # IMPORTANT: drop enum last
    school_category_enum.drop(op.get_bind(), checkfirst=True)