"""Phase 26 service desk and support control."""
from alembic import op
import sqlalchemy as sa
revision="0027_phase26_support"
down_revision="0026_phase25_change_control"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("support_tickets",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("ticket_number",sa.String(80),nullable=False),sa.Column("category",sa.String(48),nullable=False),sa.Column("priority",sa.String(24),nullable=False),sa.Column("title",sa.String(300),nullable=False),sa.Column("description",sa.Text(),nullable=False),sa.Column("due_date",sa.Date()),sa.Column("status",sa.String(24),nullable=False),sa.Column("evidence_document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="SET NULL")),sa.Column("resolution_document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="SET NULL")),sa.Column("resolution_note",sa.Text()),sa.Column("created_by",sa.String(255),nullable=False),sa.Column("assigned_to",sa.String(255)),sa.Column("resolved_by",sa.String(255)),sa.Column("resolved_at",sa.DateTime(timezone=True)),sa.Column("verified_by",sa.String(255)),sa.Column("verified_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("company_id","ticket_number",name="uq_support_ticket_number"))
 op.create_table("support_audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="SET NULL")),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("actor",sa.String(255),nullable=False),sa.Column("action",sa.String(120),nullable=False),sa.Column("entity_type",sa.String(80),nullable=False),sa.Column("entity_id",sa.String(100),nullable=False),sa.Column("detail",sa.JSON(),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False))
 for t,cs in {"support_tickets":("company_id","branch_id","site_id","ticket_number","category","priority","due_date","status"),"support_audit_events":("company_id","branch_id","site_id","action","occurred_at")}.items():
  for c in cs:op.create_index(f"ix_{t}_{c}",t,[c])
def downgrade():
 for t in ("support_audit_events","support_tickets"):
  for i in [r["name"] for r in sa.inspect(op.get_bind()).get_indexes(t)]:op.drop_index(i,table_name=t)
  op.drop_table(t)
