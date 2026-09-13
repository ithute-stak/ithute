"""use registrar nameserver delegation for all managed DNS ownership proof

Revision ID: 0019_managed_dns_ns
Revises: 0018_domain_verification_method
"""

from alembic import op

revision = "0019_managed_dns_ns"
down_revision = "0018_domain_verification_method"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Full-zone Platform DNS ownership is proved by changing the parent-zone
    # delegation to Ithute. Convert any pending managed migrations that were
    # created under the older TXT-before-cutover policy so operators are not
    # asked to publish a verification string at Zeecom/Cloudflare first.
    op.execute(
        "UPDATE domains "
        "SET verification_method = 'nameserver', verification_token_hint = 'not-needed' "
        "WHERE status = 'pending_verification' "
        "AND dns_mode = 'platform' "
        "AND ownership_verified_at IS NULL"
    )


def downgrade() -> None:
    # This is an ownership-policy data migration. Reintroducing TXT challenges on
    # downgrade would invalidate legitimate delegation workflows, so leave the
    # stored method intact; older application code already understands both values.
    pass
