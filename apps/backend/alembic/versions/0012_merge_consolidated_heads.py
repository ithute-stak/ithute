"""merge consolidated feature heads

Revision ID: 0012_merge_consolidated_heads
Revises: 0011_ithute_central_auth_link, 0011_ithute_edge_platform, 0011_auth_recovery
"""

revision = "0012_merge_consolidated_heads"
down_revision = (
    "0011_ithute_central_auth_link",
    "0011_ithute_edge_platform",
    "0011_auth_recovery",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
