"""commercial business operations

Revision ID: 0008_commercial_business
Revises: 0007_billing_operations
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_commercial_business"
down_revision = "0007_billing_operations"
branch_labels = None
depends_on = None

support_status = postgresql.ENUM("open", "in_progress", "pending_customer", "resolved", "closed", name="supportticketstatus")
support_priority = postgresql.ENUM("low", "normal", "high", "urgent", name="supportticketpriority")
incident_status = postgresql.ENUM("investigating", "identified", "monitoring", "resolved", name="serviceincidentstatus")
incident_impact = postgresql.ENUM("minor", "major", "critical", name="serviceincidentimpact")


def upgrade() -> None:
    bind = op.get_bind()
    support_status.create(bind, checkfirst=True)
    support_priority.create(bind, checkfirst=True)
    incident_status.create(bind, checkfirst=True)
    incident_impact.create(bind, checkfirst=True)

    op.create_table(
        "customer_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("billing_email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=60), nullable=True),
        sa.Column("address_line1", sa.String(length=200), nullable=True),
        sa.Column("address_line2", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=False, server_default="Lesotho"),
        sa.Column("company_registration_number", sa.String(length=120), nullable=True),
        sa.Column("tax_number", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", name="uq_customer_profile_tenant"),
    )
    op.create_index("ix_customer_profiles_tenant_id", "customer_profiles", ["tenant_id"])

    op.create_table(
        "support_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("ticket_number", sa.String(length=40), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="general"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", postgresql.ENUM("open", "in_progress", "pending_customer", "resolved", "closed", name="supportticketstatus", create_type=False), nullable=False, server_default="open"),
        sa.Column("priority", postgresql.ENUM("low", "normal", "high", "urgent", name="supportticketpriority", create_type=False), nullable=False, server_default="normal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ticket_number", name="uq_support_ticket_number"),
    )
    op.create_index("ix_support_tickets_ticket_number", "support_tickets", ["ticket_number"], unique=True)
    op.create_index("ix_support_tickets_tenant_id", "support_tickets", ["tenant_id"])
    op.create_index("ix_support_tickets_created_by_user_id", "support_tickets", ["created_by_user_id"])
    op.create_index("ix_support_tickets_assigned_to_user_id", "support_tickets", ["assigned_to_user_id"])
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])
    op.create_index("ix_support_tickets_priority", "support_tickets", ["priority"])
    op.create_index("ix_support_tickets_created_at", "support_tickets", ["created_at"])

    op.create_table(
        "support_ticket_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_role", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_support_ticket_messages_ticket_id", "support_ticket_messages", ["ticket_id"])
    op.create_index("ix_support_ticket_messages_author_user_id", "support_ticket_messages", ["author_user_id"])
    op.create_index("ix_support_ticket_messages_created_at", "support_ticket_messages", ["created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=False, server_default="general"),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(length=500), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "service_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", postgresql.ENUM("investigating", "identified", "monitoring", "resolved", name="serviceincidentstatus", create_type=False), nullable=False, server_default="investigating"),
        sa.Column("impact", postgresql.ENUM("minor", "major", "critical", name="serviceincidentimpact", create_type=False), nullable=False, server_default="minor"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_service_incidents_status", "service_incidents", ["status"])
    op.create_index("ix_service_incidents_impact", "service_incidents", ["impact"])
    op.create_index("ix_service_incidents_started_at", "service_incidents", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_service_incidents_started_at", table_name="service_incidents")
    op.drop_index("ix_service_incidents_impact", table_name="service_incidents")
    op.drop_index("ix_service_incidents_status", table_name="service_incidents")
    op.drop_table("service_incidents")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_tenant_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_support_ticket_messages_created_at", table_name="support_ticket_messages")
    op.drop_index("ix_support_ticket_messages_author_user_id", table_name="support_ticket_messages")
    op.drop_index("ix_support_ticket_messages_ticket_id", table_name="support_ticket_messages")
    op.drop_table("support_ticket_messages")
    op.drop_index("ix_support_tickets_created_at", table_name="support_tickets")
    op.drop_index("ix_support_tickets_priority", table_name="support_tickets")
    op.drop_index("ix_support_tickets_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_assigned_to_user_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_created_by_user_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_tenant_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_ticket_number", table_name="support_tickets")
    op.drop_table("support_tickets")
    op.drop_index("ix_customer_profiles_tenant_id", table_name="customer_profiles")
    op.drop_table("customer_profiles")
    bind = op.get_bind()
    incident_impact.drop(bind, checkfirst=True)
    incident_status.drop(bind, checkfirst=True)
    support_priority.drop(bind, checkfirst=True)
    support_status.drop(bind, checkfirst=True)
