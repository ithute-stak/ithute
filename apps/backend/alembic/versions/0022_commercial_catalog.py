"""add monthly commercial package catalogue

Revision ID: 0022_commercial_catalog
Revises: 0021_hosting_operations
"""

import uuid

from alembic import op
import sqlalchemy as sa

revision = "0022_commercial_catalog"
down_revision = "0021_hosting_operations"
branch_labels = None
depends_on = None


_COMMERCIAL_COLUMNS = (
    sa.Column("product_category", sa.String(length=80), nullable=False, server_default="Website & Hosting"),
    sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
    sa.Column("website_pages", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("includes_website_design", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("includes_logo_design", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("includes_brand_guide", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("includes_company_profile", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("includes_letterhead", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("includes_page_headers_footers", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("includes_business_templates", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("included_revisions", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("content_updates_per_month", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("support_level", sa.String(length=40), nullable=False, server_default="standard"),
    sa.Column("minimum_term_months", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("price_from", sa.Boolean(), nullable=False, server_default=sa.false()),
)


def _commercial_values(**overrides):
    values = {
        "product_category": "Website & Hosting",
        "description": "",
        "website_pages": 0,
        "includes_website_design": False,
        "includes_logo_design": False,
        "includes_brand_guide": False,
        "includes_company_profile": False,
        "includes_letterhead": False,
        "includes_page_headers_footers": False,
        "includes_business_templates": False,
        "included_revisions": 0,
        "content_updates_per_month": 0,
        "support_level": "standard",
        "minimum_term_months": 1,
        "price_from": False,
    }
    values.update(overrides)
    return values


def upgrade() -> None:
    for column in _COMMERCIAL_COLUMNS:
        op.add_column("billing_plans", column)

    connection = op.get_bind()
    plans = sa.table(
        "billing_plans",
        sa.column("id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("currency", sa.String()),
        sa.column("monthly_price_minor", sa.Integer()),
        sa.column("included_mailboxes", sa.Integer()),
        sa.column("included_domains", sa.Integer()),
        sa.column("included_storage_mb", sa.Integer()),
        sa.column("max_api_keys", sa.Integer()),
        sa.column("included_hosted_projects", sa.Integer()),
        sa.column("hosting_storage_mb", sa.Integer()),
        sa.column("hosting_memory_mb_per_project", sa.Integer()),
        sa.column("hosting_cpu_millicores_per_project", sa.Integer()),
        sa.column("hosting_pids_per_project", sa.Integer()),
        sa.column("product_category", sa.String()),
        sa.column("description", sa.String()),
        sa.column("website_pages", sa.Integer()),
        sa.column("includes_website_design", sa.Boolean()),
        sa.column("includes_logo_design", sa.Boolean()),
        sa.column("includes_brand_guide", sa.Boolean()),
        sa.column("includes_company_profile", sa.Boolean()),
        sa.column("includes_letterhead", sa.Boolean()),
        sa.column("includes_page_headers_footers", sa.Boolean()),
        sa.column("includes_business_templates", sa.Boolean()),
        sa.column("included_revisions", sa.Integer()),
        sa.column("content_updates_per_month", sa.Integer()),
        sa.column("support_level", sa.String()),
        sa.column("minimum_term_months", sa.Integer()),
        sa.column("price_from", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
    )

    # Reprice the three canonical plans but deliberately do not reduce any of
    # their existing hosting/email entitlements. Existing subscriptions retain
    # the capacity they already rely on.
    existing_updates = {
        "starter": {
            "name": "Ithute Start",
            "monthly_price_minor": 18_500,
            **_commercial_values(
                description="Professional starter website, hosting, business email and essential brand setup.",
                website_pages=1,
                includes_website_design=True,
                includes_logo_design=True,
                includes_page_headers_footers=True,
                included_revisions=1,
                support_level="standard",
                minimum_term_months=12,
            ),
        },
        "business": {
            "name": "Ithute Business",
            "monthly_price_minor": 49_500,
            **_commercial_values(
                description="Complete SME website, hosting and corporate identity package with business document templates.",
                website_pages=8,
                includes_website_design=True,
                includes_logo_design=True,
                includes_brand_guide=True,
                includes_company_profile=True,
                includes_letterhead=True,
                includes_page_headers_footers=True,
                includes_business_templates=True,
                included_revisions=3,
                content_updates_per_month=2,
                support_level="priority",
                minimum_term_months=12,
            ),
        },
        "enterprise": {
            "name": "Ithute Enterprise",
            "monthly_price_minor": 150_000,
            **_commercial_values(
                description="Custom digital presence, managed systems, hosting and full corporate branding for larger organizations.",
                website_pages=20,
                includes_website_design=True,
                includes_logo_design=True,
                includes_brand_guide=True,
                includes_company_profile=True,
                includes_letterhead=True,
                includes_page_headers_footers=True,
                includes_business_templates=True,
                included_revisions=8,
                content_updates_per_month=8,
                support_level="dedicated",
                minimum_term_months=12,
                price_from=True,
            ),
        },
    }
    for code, values in existing_updates.items():
        connection.execute(plans.update().where(plans.c.code == code).values(**values))

    existing_codes = set(connection.execute(sa.select(plans.c.code)).scalars())
    additions = [
        {
            "id": uuid.uuid4(),
            "code": "grow",
            "name": "Ithute Grow",
            "currency": "LSL",
            "monthly_price_minor": 29_500,
            "included_mailboxes": 15,
            "included_domains": 3,
            "included_storage_mb": 75 * 1024,
            "max_api_keys": 5,
            "included_hosted_projects": 1,
            "hosting_storage_mb": 2 * 1024,
            "hosting_memory_mb_per_project": 768,
            "hosting_cpu_millicores_per_project": 750,
            "hosting_pids_per_project": 192,
            **_commercial_values(
                description="Growing-business website and brand package with professional documents and light monthly content support.",
                website_pages=5,
                includes_website_design=True,
                includes_logo_design=True,
                includes_brand_guide=True,
                includes_letterhead=True,
                includes_page_headers_footers=True,
                included_revisions=2,
                content_updates_per_month=1,
                support_level="standard",
                minimum_term_months=12,
            ),
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "code": "professional",
            "name": "Ithute Professional",
            "currency": "LSL",
            "monthly_price_minor": 79_500,
            "included_mailboxes": 75,
            "included_domains": 15,
            "included_storage_mb": 375 * 1024,
            "max_api_keys": 15,
            "included_hosted_projects": 5,
            "hosting_storage_mb": 8 * 1024,
            "hosting_memory_mb_per_project": 1536,
            "hosting_cpu_millicores_per_project": 1500,
            "hosting_pids_per_project": 384,
            **_commercial_values(
                description="Advanced website and managed-system package with full brand identity, company profile and priority support.",
                website_pages=12,
                includes_website_design=True,
                includes_logo_design=True,
                includes_brand_guide=True,
                includes_company_profile=True,
                includes_letterhead=True,
                includes_page_headers_footers=True,
                includes_business_templates=True,
                included_revisions=5,
                content_updates_per_month=4,
                support_level="priority",
                minimum_term_months=12,
            ),
            "is_active": True,
        },
    ]
    for values in additions:
        if values["code"] not in existing_codes:
            connection.execute(plans.insert().values(**values))


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM billing_plans p WHERE p.code IN ('grow', 'professional') "
            "AND NOT EXISTS (SELECT 1 FROM tenant_subscriptions s WHERE s.plan_id = p.id)"
        )
    )
    for name in reversed([column.name for column in _COMMERCIAL_COLUMNS]):
        op.drop_column("billing_plans", name)
