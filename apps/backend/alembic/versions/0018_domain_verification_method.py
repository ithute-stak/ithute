"""store TXT versus nameserver domain verification method

Revision ID: 0018_domain_verification_method
Revises: 0017_webmail_productivity
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_domain_verification_method"
down_revision = "0017_webmail_productivity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "domains",
        sa.Column("verification_method", sa.String(length=20), nullable=False, server_default="txt"),
    )
    # Platform domains that were already pending before this distinction existed
    # were previously allowed to prove ownership through nameserver delegation.
    # Preserve that safe path and remove the misleading TXT requirement from them.
    op.execute(
        "UPDATE domains SET verification_method = 'nameserver' "
        "WHERE status = 'pending_verification' AND dns_mode = 'platform'"
    )


def downgrade() -> None:
    op.drop_column("domains", "verification_method")
