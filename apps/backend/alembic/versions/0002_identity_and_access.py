"""identity and access
Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ROLE_VALUES = ("tenant_admin", "dns_admin", "mail_admin", "auditor", "member")


def upgrade():
    bind = op.get_bind()
    membership_role = postgresql.ENUM(*ROLE_VALUES, name="membershiprole", create_type=False)
    membership_status = postgresql.ENUM("active", "suspended", name="membershipstatus", create_type=False)
    postgresql.ENUM(*ROLE_VALUES, name="membershiprole").create(bind, checkfirst=True)
    postgresql.ENUM("active", "suspended", name="membershipstatus").create(bind, checkfirst=True)

    duplicate = bind.execute(sa.text(
        "SELECT lower(email), count(*) FROM users GROUP BY lower(email) HAVING count(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            "Phase 2 requires globally unique user email addresses. "
            f"Resolve duplicate identity {duplicate[0]!r} before upgrading."
        )

    op.execute("UPDATE users SET email = lower(email)")
    op.add_column("users", sa.Column("is_platform_owner", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("mfa_secret", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"))
    op.execute("UPDATE users SET is_platform_owner = true WHERE role = 'platform_owner'")

    op.create_table(
        "tenant_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", membership_role, nullable=False),
        sa.Column("status", membership_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
    )
    op.create_index("ix_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_memberships_user_id", "tenant_memberships", ["user_id"])
    op.execute("""
        INSERT INTO tenant_memberships (id, tenant_id, user_id, role, status)
        SELECT gen_random_uuid(), tenant_id, id,
               CASE WHEN role = 'tenant_admin' THEN 'tenant_admin'::membershiprole ELSE 'member'::membershiprole END,
               'active'::membershipstatus
        FROM users WHERE tenant_id IS NOT NULL
    """)

    op.drop_constraint("uq_user_tenant_email", "users", type_="unique")
    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_column("users", "tenant_id")
    op.drop_column("users", "role")
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("refresh_token_hash"),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_refresh_token_hash", "user_sessions", ["refresh_token_hash"])

    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", membership_role, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_invitations_tenant_id", "invitations", ["tenant_id"])
    op.create_index("ix_invitations_email", "invitations", ["email"])

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scopes", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_owner_user_id", "api_keys", ["owner_user_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])
    op.add_column("audit_logs", sa.Column("metadata_json", sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    multiple = bind.execute(sa.text(
        "SELECT user_id, count(*) FROM tenant_memberships GROUP BY user_id HAVING count(*) > 1 LIMIT 1"
    )).first()
    if multiple:
        raise RuntimeError(
            "Cannot downgrade Phase 2 while a user belongs to multiple tenants. "
            "Remove extra memberships or restore from a pre-Phase-2 backup."
        )

    op.drop_column("audit_logs", "metadata_json")
    op.drop_table("api_keys")
    op.drop_table("invitations")
    op.drop_table("user_sessions")

    user_role = postgresql.ENUM("platform_owner", "tenant_admin", "member", name="userrole", create_type=False)
    op.add_column("users", sa.Column("role", user_role, nullable=True))
    op.add_column("users", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_users_tenant_id_tenants", "users", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.execute("""
        UPDATE users u
        SET tenant_id = m.tenant_id,
            role = CASE WHEN m.role = 'tenant_admin' THEN 'tenant_admin'::userrole ELSE 'member'::userrole END
        FROM tenant_memberships m
        WHERE m.user_id = u.id
    """)
    op.execute("UPDATE users SET role = 'platform_owner'::userrole WHERE is_platform_owner = true")
    op.execute("UPDATE users SET role = 'member'::userrole WHERE role IS NULL")
    op.alter_column("users", "role", nullable=False)

    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_unique_constraint("uq_user_tenant_email", "users", ["tenant_id", "email"])
    op.drop_table("tenant_memberships")
    op.drop_column("users", "session_version")
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "is_platform_owner")
    postgresql.ENUM(name="membershipstatus").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="membershiprole").drop(op.get_bind(), checkfirst=True)
