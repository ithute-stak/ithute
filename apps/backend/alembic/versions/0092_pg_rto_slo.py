"""add PostgreSQL RTO and SLO policy

Revision ID: 0092_pg_rto_slo
Revises: 0091_pg_rpo_policy
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0092_pg_rto_slo"
down_revision = "0091_pg_rpo_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("auto_failover_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("rto_target_seconds", sa.Integer(), nullable=False, server_default="300"),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("detection_budget_seconds", sa.Integer(), nullable=False, server_default="90"),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("fencing_budget_seconds", sa.Integer(), nullable=False, server_default="120"),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("promotion_budget_seconds", sa.Integer(), nullable=False, server_default="60"),
    )
    op.add_column(
        "hosting_postgres_replication_groups",
        sa.Column("repair_budget_seconds", sa.Integer(), nullable=False, server_default="900"),
    )
    op.create_check_constraint(
        "ck_pg_group_rto_target",
        "hosting_postgres_replication_groups",
        "rto_target_seconds >= 30 AND rto_target_seconds <= 86400",
    )
    op.create_check_constraint(
        "ck_pg_group_detection_budget",
        "hosting_postgres_replication_groups",
        "detection_budget_seconds >= 15 AND detection_budget_seconds <= 3600",
    )
    op.create_check_constraint(
        "ck_pg_group_fencing_budget",
        "hosting_postgres_replication_groups",
        "fencing_budget_seconds >= 15 AND fencing_budget_seconds <= 3600",
    )
    op.create_check_constraint(
        "ck_pg_group_promotion_budget",
        "hosting_postgres_replication_groups",
        "promotion_budget_seconds >= 15 AND promotion_budget_seconds <= 3600",
    )
    op.create_check_constraint(
        "ck_pg_group_repair_budget",
        "hosting_postgres_replication_groups",
        "repair_budget_seconds >= 60 AND repair_budget_seconds <= 86400",
    )

    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("failure_detected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("fence_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("promotion_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("service_restored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("redundancy_restored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("trigger", sa.String(length=24), nullable=False, server_default="manual"),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("rto_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("rto_met", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "hosting_postgres_group_failovers",
        sa.Column("repair_slo_met", sa.Boolean(), nullable=True),
    )
    op.create_check_constraint(
        "ck_pg_group_failover_trigger",
        "hosting_postgres_group_failovers",
        "trigger IN ('manual','health_automation')",
    )
    op.create_check_constraint(
        "ck_pg_group_failover_rto_seconds",
        "hosting_postgres_group_failovers",
        "rto_seconds IS NULL OR rto_seconds >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_pg_group_failover_rto_seconds", "hosting_postgres_group_failovers", type_="check")
    op.drop_constraint("ck_pg_group_failover_trigger", "hosting_postgres_group_failovers", type_="check")
    op.drop_column("hosting_postgres_group_failovers", "repair_slo_met")
    op.drop_column("hosting_postgres_group_failovers", "rto_met")
    op.drop_column("hosting_postgres_group_failovers", "rto_seconds")
    op.drop_column("hosting_postgres_group_failovers", "trigger")
    op.drop_column("hosting_postgres_group_failovers", "redundancy_restored_at")
    op.drop_column("hosting_postgres_group_failovers", "service_restored_at")
    op.drop_column("hosting_postgres_group_failovers", "promotion_started_at")
    op.drop_column("hosting_postgres_group_failovers", "fence_started_at")
    op.drop_column("hosting_postgres_group_failovers", "failure_detected_at")

    op.drop_constraint("ck_pg_group_repair_budget", "hosting_postgres_replication_groups", type_="check")
    op.drop_constraint("ck_pg_group_promotion_budget", "hosting_postgres_replication_groups", type_="check")
    op.drop_constraint("ck_pg_group_fencing_budget", "hosting_postgres_replication_groups", type_="check")
    op.drop_constraint("ck_pg_group_detection_budget", "hosting_postgres_replication_groups", type_="check")
    op.drop_constraint("ck_pg_group_rto_target", "hosting_postgres_replication_groups", type_="check")
    op.drop_column("hosting_postgres_replication_groups", "repair_budget_seconds")
    op.drop_column("hosting_postgres_replication_groups", "promotion_budget_seconds")
    op.drop_column("hosting_postgres_replication_groups", "fencing_budget_seconds")
    op.drop_column("hosting_postgres_replication_groups", "detection_budget_seconds")
    op.drop_column("hosting_postgres_replication_groups", "rto_target_seconds")
    op.drop_column("hosting_postgres_replication_groups", "auto_failover_enabled")
