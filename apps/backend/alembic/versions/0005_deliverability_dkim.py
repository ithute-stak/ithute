"""phase 8 deliverability dkim keys

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dkim_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("selector", sa.String(length=63), nullable=False),
        sa.Column("algorithm", sa.String(length=32), nullable=False, server_default="rsa-sha256"),
        sa.Column("public_key_b64", sa.String(length=4096), nullable=False),
        sa.Column("private_key_encrypted", sa.String(length=8192), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("domain_id", "selector", name="uq_dkim_domain_selector"),
    )
    op.create_index("ix_dkim_keys_tenant_id", "dkim_keys", ["tenant_id"])
    op.create_index("ix_dkim_keys_domain_id", "dkim_keys", ["domain_id"])


def downgrade() -> None:
    op.drop_index("ix_dkim_keys_domain_id", table_name="dkim_keys")
    op.drop_index("ix_dkim_keys_tenant_id", table_name="dkim_keys")
    op.drop_table("dkim_keys")
