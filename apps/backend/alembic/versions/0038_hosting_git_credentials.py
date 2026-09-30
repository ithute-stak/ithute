"""add encrypted hosting Git source credentials

Revision ID: 0038_hosting_git_credentials
Revises: 0037_hosting_database_lifecycle
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0038_hosting_git_credentials"
down_revision = "0037_hosting_database_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_source_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=24), nullable=False),
        sa.Column("auth_type", sa.String(length=24), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("provider IN ('github','gitlab','bitbucket','generic')", name="ck_hosting_source_credential_provider"),
        sa.CheckConstraint("auth_type IN ('https_token','ssh_key')", name="ck_hosting_source_credential_auth_type"),
        sa.CheckConstraint("status IN ('active','revoked')", name="ck_hosting_source_credential_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["hosting_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name", name="uq_hosting_source_credential_project_name"),
    )
    op.create_index("ix_hosting_source_credentials_tenant_id", "hosting_source_credentials", ["tenant_id"])
    op.create_index("ix_hosting_source_credentials_project_id", "hosting_source_credentials", ["project_id"])
    op.create_index("ix_hosting_source_credentials_status", "hosting_source_credentials", ["status"])

    op.add_column("hosting_sources", sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_hosting_sources_credential_id",
        "hosting_sources",
        "hosting_source_credentials",
        ["credential_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_hosting_sources_credential_id", "hosting_sources", ["credential_id"])


def downgrade() -> None:
    op.drop_index("ix_hosting_sources_credential_id", table_name="hosting_sources")
    op.drop_constraint("fk_hosting_sources_credential_id", "hosting_sources", type_="foreignkey")
    op.drop_column("hosting_sources", "credential_id")
    op.drop_table("hosting_source_credentials")
