"""Scope platform mail domain grants to explicit mailbox namespaces.

Revision ID: 0024_mail_namespace
Revises: 0023_platform_mail_provisioning
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_mail_namespace"
down_revision = "0023_platform_mail_provisioning"
branch_labels = None
depends_on = None


_LEGACY_DISABLED_PREFIX = "legacy-disabled-"


def upgrade() -> None:
    op.add_column(
        "platform_mail_domain_grants",
        sa.Column("local_part_prefix", sa.String(length=32), nullable=True),
    )

    # Whole-domain delegation is no longer safe. Existing grants are deliberately
    # disabled instead of silently inheriting a broad namespace. A platform owner
    # must explicitly re-save each intended grant with a constrained prefix.
    op.execute(
        sa.text(
            "UPDATE platform_mail_domain_grants "
            "SET active = false, local_part_prefix = :prefix"
        ).bindparams(prefix=_LEGACY_DISABLED_PREFIX)
    )
    op.alter_column(
        "platform_mail_domain_grants",
        "local_part_prefix",
        existing_type=sa.String(length=32),
        nullable=False,
    )


def downgrade() -> None:
    # Do not reactivate grants automatically: a row that was inactive before this
    # migration cannot be distinguished safely from one disabled by the migration.
    op.drop_column("platform_mail_domain_grants", "local_part_prefix")
