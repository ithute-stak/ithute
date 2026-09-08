"""Phase 24 delegated authority and approval limits."""
from alembic import op
import sqlalchemy as sa
revision = "0025_phase24_authority"
down_revision = "0024_phase23_data_quality"
branch_labels = None
depends_on = None
def upgrade()->None:
 op.create_table("authority_limits",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("role_id",sa.Integer(),sa.ForeignKey("roles.id",ondelete="RESTRICT"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("limit_number",sa.String(80),nullable=False),sa.Column("module",sa.String(80),nullable=False),sa.Column("transaction_type",sa.String(80),nullable=False),sa.Column("minimum_amount",sa.Numeric(18,2),nullable=False),sa.Column("maximum_amount",sa.Numeric(18,2),nullable=False),sa.Column("currency",sa.String(8),nullable=False),sa.Column("effective_from",sa.Date(),nullable=False),sa.Column("effective_to",sa.Date()),sa.Column("status",sa.String(24),nullable=False),sa.Column("document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="SET NULL")),sa.Column("notes",sa.Text()),sa.Column("prepared_by",sa.String(255),nullable=False),sa.Column("submitted_at",sa.DateTime(timezone=True)),sa.Column("approved_at",sa.DateTime(timezone=True)),sa.Column("approved_by",sa.String(255)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("company_id","role_id","branch_id","site_id","module","transaction_type","effective_from",name="uq_authority_limit_scope"))
 op.create_table("authority_audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="SET NULL")),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("actor",sa.String(255),nullable=False),sa.Column("action",sa.String(120),nullable=False),sa.Column("entity_type",sa.String(80),nullable=False),sa.Column("entity_id",sa.String(100),nullable=False),sa.Column("detail",sa.JSON(),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False))
 for t,cs in {"authority_limits":("company_id","role_id","branch_id","site_id","limit_number","module","transaction_type","effective_from","effective_to","status"),"authority_audit_events":("company_id","branch_id","site_id","action","occurred_at")}.items():
  for c in cs:op.create_index(f"ix_{t}_{c}",t,[c])
def downgrade()->None:
 for t in ("authority_audit_events","authority_limits"):
  for i in [r["name"] for r in sa.inspect(op.get_bind()).get_indexes(t)]:op.drop_index(i,table_name=t)
  op.drop_table(t)
