"""Ithute edge and security control plane

Revision ID: 0011_ithute_edge_platform
Revises: 0010_platform_self_domain
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_ithute_edge_platform"
down_revision = "0010_platform_self_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edge_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hostname", sa.String(length=253), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False, server_default="dns_only"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("cache_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("waf_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bot_protection_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_shield_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("access_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True),
        sa.Column("tls_mode", sa.String(length=24), nullable=False, server_default="automatic"),
        sa.Column("minimum_tls_version", sa.String(length=16), nullable=False, server_default="TLSv1.2"),
        sa.Column("health_path", sa.String(length=500), nullable=False, server_default="/"),
        sa.Column("expected_status", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "hostname", name="uq_edge_application_tenant_hostname"),
        sa.CheckConstraint("mode IN ('dns_only', 'protected')", name="ck_edge_application_mode"),
        sa.CheckConstraint("rate_limit_per_minute IS NULL OR rate_limit_per_minute BETWEEN 1 AND 1000000", name="ck_edge_application_rate_limit"),
        sa.CheckConstraint("expected_status BETWEEN 100 AND 599", name="ck_edge_application_expected_status"),
    )
    op.create_index("ix_edge_applications_tenant_id", "edge_applications", ["tenant_id"])
    op.create_index("ix_edge_applications_domain_id", "edge_applications", ["domain_id"])
    op.create_index("ix_edge_applications_hostname", "edge_applications", ["hostname"])

    op.create_table(
        "edge_origins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("edge_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("failover_priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("health_path", sa.String(length=500), nullable=False, server_default="/"),
        sa.Column("expected_status", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("application_id", "name", name="uq_edge_origin_application_name"),
        sa.CheckConstraint("weight BETWEEN 1 AND 10000", name="ck_edge_origin_weight"),
        sa.CheckConstraint("failover_priority BETWEEN 1 AND 10000", name="ck_edge_origin_failover_priority"),
        sa.CheckConstraint("expected_status BETWEEN 100 AND 599", name="ck_edge_origin_expected_status"),
        sa.CheckConstraint("timeout_seconds BETWEEN 1 AND 30", name="ck_edge_origin_timeout"),
    )
    op.create_index("ix_edge_origins_application_id", "edge_origins", ["application_id"])

    op.create_table(
        "edge_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("edge_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("rule_type", sa.String(length=40), nullable=False),
        sa.Column("expression", sa.Text(), nullable=False, server_default="true"),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("priority BETWEEN 1 AND 100000", name="ck_edge_rule_priority"),
    )
    op.create_index("ix_edge_rules_application_id", "edge_rules", ["application_id"])
    op.create_index("ix_edge_rules_rule_type", "edge_rules", ["rule_type"])

    op.create_table(
        "edge_inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("edge_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("edge_origins.id", ondelete="CASCADE"), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("healthy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("resolved_ip", sa.String(length=64), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tls_version", sa.String(length=40), nullable=True),
        sa.Column("cipher", sa.String(length=120), nullable=True),
        sa.Column("certificate_issuer", sa.String(length=500), nullable=True),
        sa.Column("certificate_not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("certificate_days_remaining", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
    )
    op.create_index("ix_edge_inspections_application_id", "edge_inspections", ["application_id"])
    op.create_index("ix_edge_inspections_origin_id", "edge_inspections", ["origin_id"])
    op.create_index("ix_edge_inspections_checked_at", "edge_inspections", ["checked_at"])

    op.create_table(
        "dns_zone_analytics_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("zone_kind", sa.String(length=40), nullable=True),
        sa.Column("serial", sa.Integer(), nullable=True),
        sa.Column("dnssec_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rrset_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("type_counts_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_dns_zone_analytics_snapshots_tenant_id", "dns_zone_analytics_snapshots", ["tenant_id"])
    op.create_index("ix_dns_zone_analytics_snapshots_domain_id", "dns_zone_analytics_snapshots", ["domain_id"])
    op.create_index("ix_dns_zone_analytics_snapshots_captured_at", "dns_zone_analytics_snapshots", ["captured_at"])


def downgrade() -> None:
    op.drop_table("dns_zone_analytics_snapshots")
    op.drop_table("edge_inspections")
    op.drop_table("edge_rules")
    op.drop_table("edge_origins")
    op.drop_table("edge_applications")
