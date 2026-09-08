from alembic import op
import sqlalchemy as sa
revision="0036_phase35_automation"
down_revision="0035_phase34_contract_ctrl"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("automation_rules",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE")),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="CASCADE")),sa.Column("name",sa.String(160)),sa.Column("trigger",sa.String(80)),sa.Column("channel",sa.String(40)),sa.Column("status",sa.String(24)),sa.Column("created_by",sa.String(255)),sa.Column("created_at",sa.DateTime(timezone=True)))
 op.create_table("automation_audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE")),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="SET NULL")),sa.Column("actor",sa.String(255)),sa.Column("action",sa.String(120)),sa.Column("detail",sa.JSON()),sa.Column("occurred_at",sa.DateTime(timezone=True)))
def downgrade():op.drop_table("automation_audit_events");op.drop_table("automation_rules")
