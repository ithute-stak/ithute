"""hosting catalog, addons and edge route deployments

Revision ID: 0049_hosting_catalog
Revises: 0048_customer_approvals
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0049_hosting_catalog"
down_revision = "0048_customer_approvals"
branch_labels = None
depends_on = None


# These codes are intentionally namespaced. Earlier commercial catalogues use
# codes such as grow/business/professional/enterprise and may already have live
# subscriptions. A migration must never rewrite an existing customer's package
# contract just because Ithute launches a new hosting catalogue.
PACKAGES = (
    # code, name, annual LSL minor, setup, mailboxes, domains, mail MB, API keys,
    # projects, app MB, RAM/project, CPU millicores, PIDs, DBs, DB MB, source MB, support, sort
    ("ithute-start", "Ithute Start", 84000, 10000, 18, 1, 36864, 3, 1, 2048, 512, 500, 128, 2, 2048, 2048, "standard", 10),
    ("ithute-grow", "Ithute Grow", 168000, 10000, 50, 3, 102400, 5, 3, 8192, 768, 750, 192, 5, 8192, 8192, "standard", 20),
    ("ithute-business", "Ithute Business", 288000, 10000, 100, 10, 204800, 10, 8, 20480, 1024, 1000, 256, 10, 20480, 20480, "priority", 30),
    ("ithute-professional", "Ithute Professional", 504000, 15000, 200, 20, 409600, 20, 15, 40960, 1536, 1500, 384, 20, 40960, 40960, "priority", 40),
    ("ithute-enterprise", "Ithute Enterprise", 900000, 25000, 500, 40, 1024000, 50, 30, 81920, 2048, 2000, 512, 40, 81920, 81920, "dedicated", 50),
    ("ithute-ultimate", "Ithute Ultimate", 1500000, 50000, 1000, 80, 2048000, 100, 50, 153600, 3072, 3000, 768, 80, 153600, 153600, "dedicated", 60),
)

PACKAGE_CODES = tuple(row[0] for row in PACKAGES)
LEGACY_CODES = ("starter", "grow", "business", "professional", "enterprise")


def upgrade():
    op.add_column("billing_plans", sa.Column("annual_price_minor", sa.Integer(), nullable=True))
    op.add_column("billing_plans", sa.Column("setup_fee_minor", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("billing_plans", sa.Column("customer_visible", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("billing_plans", sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("billing_plans", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"))

    op.create_table(
        "billing_addons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("name", sa.String(140), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("currency", sa.String(3), nullable=False, server_default="LSL"),
        sa.Column("monthly_price_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("annual_price_minor", sa.Integer(), nullable=True),
        sa.Column("setup_fee_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resource_key", sa.String(60), nullable=False),
        sa.Column("amount_per_quantity", sa.Integer(), nullable=False),
        sa.Column("unit_label", sa.String(40), nullable=False),
        sa.Column("max_quantity", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("customer_visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_billing_addon_code"),
    )
    op.create_index("ix_billing_addons_code", "billing_addons", ["code"])
    op.create_index("ix_billing_addons_resource_key", "billing_addons", ["resource_key"])

    op.create_table(
        "tenant_addons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("addon_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("billing_addons.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "addon_id", name="uq_tenant_addon"),
    )
    op.create_index("ix_tenant_addons_tenant_id", "tenant_addons", ["tenant_id"])
    op.create_index("ix_tenant_addons_addon_id", "tenant_addons", ["addon_id"])
    op.create_index("ix_tenant_addons_status", "tenant_addons", ["status"])

    op.create_table(
        "edge_route_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("edge_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_dns"),
        sa.Column("expected_ips_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("observed_ips_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("caddy_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("application_id", name="uq_edge_route_application"),
    )
    op.create_index("ix_edge_route_deployments_application_id", "edge_route_deployments", ["application_id"])
    op.create_index("ix_edge_route_deployments_status", "edge_route_deployments", ["status"])

    bind = op.get_bind()

    # Keep historical rows and subscriptions untouched. They remain available to
    # existing tenants through their subscription IDs, but are hidden from the
    # new /public/pricing catalogue so new customers see one coherent product family.
    bind.execute(
        sa.text("UPDATE billing_plans SET customer_visible = false WHERE code = ANY(:codes)"),
        {"codes": list(LEGACY_CODES)},
    )

    for row in PACKAGES:
        (
            code, name, annual_price, setup_fee, mailboxes, domains, mail_storage,
            api_keys, projects, hosting_storage, memory, cpu, pids, db_limit,
            db_storage, source_storage, support, sort_order,
        ) = row
        monthly = max(0, annual_price // 12)
        bind.execute(sa.text("""
            INSERT INTO billing_plans (
                id, code, name, currency, monthly_price_minor, annual_price_minor,
                setup_fee_minor, included_mailboxes, included_domains,
                included_storage_mb, max_api_keys, included_hosted_projects,
                hosting_storage_mb, hosting_memory_mb_per_project,
                hosting_cpu_millicores_per_project, hosting_pids_per_project,
                hosting_database_limit, hosting_database_storage_mb,
                hosting_source_storage_mb, product_category, description,
                support_level, minimum_term_months, price_from, is_active,
                customer_visible, featured, sort_order
            ) VALUES (
                gen_random_uuid(), :code, :name, 'LSL', :monthly, :annual, :setup,
                :mailboxes, :domains, :mail_storage, :api_keys, :projects,
                :hosting_storage, :memory, :cpu, :pids, :db_limit, :db_storage,
                :source_storage, 'Website & Application Hosting', :description,
                :support, 12, false, true, true, :featured, :sort_order
            )
            ON CONFLICT (code) DO NOTHING
        """), {
            "code": code,
            "name": name,
            "monthly": monthly,
            "annual": annual_price,
            "setup": setup_fee,
            "mailboxes": mailboxes,
            "domains": domains,
            "mail_storage": mail_storage,
            "api_keys": api_keys,
            "projects": projects,
            "hosting_storage": hosting_storage,
            "memory": memory,
            "cpu": cpu,
            "pids": pids,
            "db_limit": db_limit,
            "db_storage": db_storage,
            "source_storage": source_storage,
            "description": f"{name} managed hosting with professional email, DNS, HTTPS, Git/ZIP deployment, logs and database backups.",
            "support": support,
            "featured": code == "ithute-business",
            "sort_order": sort_order,
        })

    addon_rows = (
        ("extra-mail-10", "10 extra professional mailboxes", "mailboxes", 10, "mailboxes", 5000, 50000, 10),
        ("extra-app-storage-5gb", "5 GB extra application storage", "hosting_storage_mb", 5120, "GB", 5000, 50000, 20),
        ("extra-site", "1 extra hosted website/application", "hosted_projects", 1, "site/app", 6000, 60000, 30),
        ("extra-db-2", "2 extra managed databases", "database_count", 2, "databases", 4000, 40000, 40),
        ("extra-db-storage-5gb", "5 GB extra database storage", "database_storage_mb", 5120, "GB", 5000, 50000, 50),
        ("extra-domain", "1 extra managed domain", "domains", 1, "domain", 2500, 25000, 60),
        ("extra-source-storage-5gb", "5 GB extra Git/ZIP source storage", "source_storage_mb", 5120, "GB", 3500, 35000, 70),
    )
    for code, name, resource_key, amount, unit, monthly, annual, sort_order in addon_rows:
        bind.execute(sa.text("""
            INSERT INTO billing_addons (
                id, code, name, description, currency, monthly_price_minor,
                annual_price_minor, setup_fee_minor, resource_key,
                amount_per_quantity, unit_label, max_quantity,
                customer_visible, is_active, sort_order
            ) VALUES (
                gen_random_uuid(), :code, :name, :name, 'LSL', :monthly,
                :annual, 0, :resource_key, :amount, :unit, 100, true, true, :sort_order
            ) ON CONFLICT (code) DO NOTHING
        """), {
            "code": code, "name": name, "monthly": monthly, "annual": annual,
            "resource_key": resource_key, "amount": amount, "unit": unit,
            "sort_order": sort_order,
        })


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM billing_plans WHERE code = ANY(:codes)"),
        {"codes": list(PACKAGE_CODES)},
    )
    op.drop_index("ix_edge_route_deployments_status", table_name="edge_route_deployments")
    op.drop_index("ix_edge_route_deployments_application_id", table_name="edge_route_deployments")
    op.drop_table("edge_route_deployments")
    op.drop_index("ix_tenant_addons_status", table_name="tenant_addons")
    op.drop_index("ix_tenant_addons_addon_id", table_name="tenant_addons")
    op.drop_index("ix_tenant_addons_tenant_id", table_name="tenant_addons")
    op.drop_table("tenant_addons")
    op.drop_index("ix_billing_addons_resource_key", table_name="billing_addons")
    op.drop_index("ix_billing_addons_code", table_name="billing_addons")
    op.drop_table("billing_addons")
    op.drop_column("billing_plans", "sort_order")
    op.drop_column("billing_plans", "featured")
    op.drop_column("billing_plans", "customer_visible")
    op.drop_column("billing_plans", "setup_fee_minor")
    op.drop_column("billing_plans", "annual_price_minor")
