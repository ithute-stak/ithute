"""add shared hosting databases and source records

Revision ID: 0036_shared_hosting_resources
Revises: 0035_finance_completion
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0036_shared_hosting_resources"
down_revision = "0035_finance_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosting_databases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("engine", sa.String(length=24), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=True),
        sa.Column("database_name", sa.String(length=63), nullable=False),
        sa.Column("username", sa.String(length=63), nullable=False),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("internal_host", sa.String(length=253), nullable=True),
        sa.Column("internal_port", sa.Integer(), nullable=False),
        sa.Column("storage_mb", sa.Integer(), server_default="1024", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="provisioning", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("engine IN ('postgresql','mysql')", name="ck_hosting_database_engine"),
        sa.CheckConstraint("status IN ('provisioning','ready','suspended','failed','deleting')", name="ck_hosting_database_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["hosting_projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["node_id"], ["hosting_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "engine", "database_name", name="uq_hosting_database_tenant_engine_name"),
        sa.UniqueConstraint("username", name="uq_hosting_database_username"),
    )
    for column in ["tenant_id", "project_id", "node_id", "engine", "status"]:
        op.create_index(f"ix_hosting_databases_{column}", "hosting_databases", [column])

    op.create_table(
        "hosting_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("repository_url", sa.String(length=1000), nullable=True),
        sa.Column("repository_branch", sa.String(length=160), nullable=True),
        sa.Column("repository_commit", sa.String(length=64), nullable=True),
        sa.Column("upload_object_key", sa.String(length=500), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="registered", nullable=False),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_type IN ('git','zip')", name="ck_hosting_source_type"),
        sa.CheckConstraint("status IN ('registered','uploading','ready','building','failed','superseded')", name="ck_hosting_source_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["hosting_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("upload_object_key"),
    )
    for column in ["tenant_id", "project_id", "source_type", "sha256", "status"]:
        op.create_index(f"ix_hosting_sources_{column}", "hosting_sources", [column])


def downgrade() -> None:
    op.drop_table("hosting_sources")
    op.drop_table("hosting_databases")
