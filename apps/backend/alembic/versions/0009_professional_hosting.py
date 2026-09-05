"""professional email and hosting company

Revision ID: 0009_professional_hosting
Revises: 0008_commercial_business
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_professional_hosting"
down_revision = "0008_commercial_business"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, created_at, now())")

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_token_hash"),
    )
    op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])
    op.create_index("ix_email_verification_tokens_token_hash", "email_verification_tokens", ["token_hash"], unique=True)

    op.create_table(
        "mailbox_delegates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delegate_address", sa.String(length=320), nullable=False),
        sa.Column("permissions", sa.String(length=120), nullable=False, server_default="lookup,read,write,insert,post"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", "delegate_address", name="uq_mailbox_delegate"),
    )
    op.create_index("ix_mailbox_delegates_tenant_id", "mailbox_delegates", ["tenant_id"])
    op.create_index("ix_mailbox_delegates_mailbox_id", "mailbox_delegates", ["mailbox_id"])

    op.create_table(
        "mailbox_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vacation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("vacation_subject", sa.String(length=240), nullable=True),
        sa.Column("vacation_body", sa.Text(), nullable=True),
        sa.Column("sieve_script", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", name="uq_mailbox_policy"),
    )
    op.create_index("ix_mailbox_policies_tenant_id", "mailbox_policies", ["tenant_id"])
    op.create_index("ix_mailbox_policies_mailbox_id", "mailbox_policies", ["mailbox_id"])

    op.create_table(
        "mail_migration_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_provider", sa.String(length=40), nullable=False),
        sa.Column("source_host", sa.String(length=253), nullable=False),
        sa.Column("source_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("source_username", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("folders_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("folders_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_copied", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_copied", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mail_migration_jobs_tenant_id", "mail_migration_jobs", ["tenant_id"])
    op.create_index("ix_mail_migration_jobs_mailbox_id", "mail_migration_jobs", ["mailbox_id"])
    op.create_index("ix_mail_migration_jobs_status", "mail_migration_jobs", ["status"])

    op.create_table(
        "mailbox_recovery_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("restored_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mailbox_recovery_jobs_tenant_id", "mailbox_recovery_jobs", ["tenant_id"])
    op.create_index("ix_mailbox_recovery_jobs_mailbox_id", "mailbox_recovery_jobs", ["mailbox_id"])
    op.create_index("ix_mailbox_recovery_jobs_status", "mailbox_recovery_jobs", ["status"])

    op.create_table(
        "reputation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=True),
        sa.Column("mail_ip", sa.String(length=64), nullable=False),
        sa.Column("ptr_ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fcrdns_ok", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dnsbl_hits_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reputation_snapshots_tenant_id", "reputation_snapshots", ["tenant_id"])
    op.create_index("ix_reputation_snapshots_domain_id", "reputation_snapshots", ["domain_id"])

    op.create_table(
        "reseller_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("discount_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_customers", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", name="uq_reseller_tenant"),
    )
    op.create_index("ix_reseller_accounts_tenant_id", "reseller_accounts", ["tenant_id"])

    op.create_table(
        "reseller_customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("reseller_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reseller_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("customer_tenant_id", name="uq_reseller_customer_tenant"),
    )
    op.create_index("ix_reseller_customers_reseller_id", "reseller_customers", ["reseller_id"])
    op.create_index("ix_reseller_customers_customer_tenant_id", "reseller_customers", ["customer_tenant_id"])

    op.create_table(
        "white_label_brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("reseller_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reseller_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("brand_name", sa.String(length=120), nullable=False),
        sa.Column("support_email", sa.String(length=320), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("primary_color", sa.String(length=20), nullable=True),
        sa.Column("custom_hostname", sa.String(length=253), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("reseller_id", name="uq_white_label_reseller"),
    )
    op.create_index("ix_white_label_brands_reseller_id", "white_label_brands", ["reseller_id"])

    op.create_table(
        "domain_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reseller_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reseller_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("domain_name", sa.String(length=253), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False, server_default="register"),
        sa.Column("years", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider", sa.String(length=40), nullable=False, server_default="opensrs"),
        sa.Column("provider_order_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_domain_orders_tenant_id", "domain_orders", ["tenant_id"])
    op.create_index("ix_domain_orders_reseller_id", "domain_orders", ["reseller_id"])
    op.create_index("ix_domain_orders_domain_name", "domain_orders", ["domain_name"])
    op.create_index("ix_domain_orders_status", "domain_orders", ["status"])

    op.create_table(
        "smtp_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sender_address", sa.String(length=320), nullable=True),
        sa.Column("system_managed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("username", name="uq_smtp_credential_username"),
    )
    op.create_index("ix_smtp_credentials_tenant_id", "smtp_credentials", ["tenant_id"])
    op.create_index("ix_smtp_credentials_username", "smtp_credentials", ["username"])

    op.create_table(
        "transactional_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("credential_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("smtp_credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message_id", sa.String(length=320), nullable=False),
        sa.Column("sender", sa.String(length=320), nullable=False),
        sa.Column("recipients_json", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_transactional_messages_tenant_id", "transactional_messages", ["tenant_id"])
    op.create_index("ix_transactional_messages_api_key_id", "transactional_messages", ["api_key_id"])
    op.create_index("ix_transactional_messages_credential_id", "transactional_messages", ["credential_id"])
    op.create_index("ix_transactional_messages_message_id", "transactional_messages", ["message_id"])
    op.create_index("ix_transactional_messages_status", "transactional_messages", ["status"])

    op.create_table(
        "groupware_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mailbox_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mailbox_id", name="uq_groupware_mailbox"),
    )
    op.create_index("ix_groupware_credentials_tenant_id", "groupware_credentials", ["tenant_id"])
    op.create_index("ix_groupware_credentials_mailbox_id", "groupware_credentials", ["mailbox_id"])

    op.create_table(
        "mail_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("region", sa.String(length=80), nullable=False, server_default="lesotho"),
        sa.Column("public_ip", sa.String(length=64), nullable=True),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_mail_node_name"),
    )
    op.create_index("ix_mail_nodes_status", "mail_nodes", ["status"])


def downgrade() -> None:
    op.drop_index("ix_mail_nodes_status", table_name="mail_nodes")
    op.drop_table("mail_nodes")
    op.drop_index("ix_groupware_credentials_mailbox_id", table_name="groupware_credentials")
    op.drop_index("ix_groupware_credentials_tenant_id", table_name="groupware_credentials")
    op.drop_table("groupware_credentials")
    op.drop_index("ix_transactional_messages_status", table_name="transactional_messages")
    op.drop_index("ix_transactional_messages_message_id", table_name="transactional_messages")
    op.drop_index("ix_transactional_messages_credential_id", table_name="transactional_messages")
    op.drop_index("ix_transactional_messages_api_key_id", table_name="transactional_messages")
    op.drop_index("ix_transactional_messages_tenant_id", table_name="transactional_messages")
    op.drop_table("transactional_messages")
    op.drop_index("ix_smtp_credentials_username", table_name="smtp_credentials")
    op.drop_index("ix_smtp_credentials_tenant_id", table_name="smtp_credentials")
    op.drop_table("smtp_credentials")
    op.drop_index("ix_domain_orders_status", table_name="domain_orders")
    op.drop_index("ix_domain_orders_domain_name", table_name="domain_orders")
    op.drop_index("ix_domain_orders_reseller_id", table_name="domain_orders")
    op.drop_index("ix_domain_orders_tenant_id", table_name="domain_orders")
    op.drop_table("domain_orders")
    op.drop_index("ix_white_label_brands_reseller_id", table_name="white_label_brands")
    op.drop_table("white_label_brands")
    op.drop_index("ix_reseller_customers_customer_tenant_id", table_name="reseller_customers")
    op.drop_index("ix_reseller_customers_reseller_id", table_name="reseller_customers")
    op.drop_table("reseller_customers")
    op.drop_index("ix_reseller_accounts_tenant_id", table_name="reseller_accounts")
    op.drop_table("reseller_accounts")
    op.drop_index("ix_reputation_snapshots_domain_id", table_name="reputation_snapshots")
    op.drop_index("ix_reputation_snapshots_tenant_id", table_name="reputation_snapshots")
    op.drop_table("reputation_snapshots")
    op.drop_index("ix_mailbox_recovery_jobs_status", table_name="mailbox_recovery_jobs")
    op.drop_index("ix_mailbox_recovery_jobs_mailbox_id", table_name="mailbox_recovery_jobs")
    op.drop_index("ix_mailbox_recovery_jobs_tenant_id", table_name="mailbox_recovery_jobs")
    op.drop_table("mailbox_recovery_jobs")
    op.drop_index("ix_mail_migration_jobs_status", table_name="mail_migration_jobs")
    op.drop_index("ix_mail_migration_jobs_mailbox_id", table_name="mail_migration_jobs")
    op.drop_index("ix_mail_migration_jobs_tenant_id", table_name="mail_migration_jobs")
    op.drop_table("mail_migration_jobs")
    op.drop_index("ix_mailbox_policies_mailbox_id", table_name="mailbox_policies")
    op.drop_index("ix_mailbox_policies_tenant_id", table_name="mailbox_policies")
    op.drop_table("mailbox_policies")
    op.drop_index("ix_mailbox_delegates_mailbox_id", table_name="mailbox_delegates")
    op.drop_index("ix_mailbox_delegates_tenant_id", table_name="mailbox_delegates")
    op.drop_table("mailbox_delegates")
    op.drop_index("ix_email_verification_tokens_token_hash", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_column("users", "email_verified_at")
