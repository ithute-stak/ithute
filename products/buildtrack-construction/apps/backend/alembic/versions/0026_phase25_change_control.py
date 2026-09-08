"""Phase 25 system change and release control."""
from alembic import op
import sqlalchemy as sa
revision = "0026_phase25_change_control"
down_revision = "0025_phase24_authority"
branch_labels = None
depends_on = None
def upgrade():
 op.create_table("change_requests",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("change_number",sa.String(80),nullable=False),sa.Column("title",sa.String(300),nullable=False),sa.Column("change_type",sa.String(48),nullable=False),sa.Column("risk_level",sa.String(24),nullable=False),sa.Column("description",sa.Text(),nullable=False),sa.Column("impact_assessment",sa.Text()),sa.Column("pilot_plan",sa.Text()),sa.Column("planned_release_date",sa.Date()),sa.Column("status",sa.String(24),nullable=False),sa.Column("evidence_document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="SET NULL")),sa.Column("uat_document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="SET NULL")),sa.Column("release_document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="SET NULL")),sa.Column("prepared_by",sa.String(255),nullable=False),sa.Column("submitted_at",sa.DateTime(timezone=True)),sa.Column("approved_at",sa.DateTime(timezone=True)),sa.Column("approved_by",sa.String(255)),sa.Column("released_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("company_id","change_number",name="uq_change_request_number"))
 op.create_table("change_audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="SET NULL")),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("actor",sa.String(255),nullable=False),sa.Column("action",sa.String(120),nullable=False),sa.Column("entity_type",sa.String(80),nullable=False),sa.Column("entity_id",sa.String(100),nullable=False),sa.Column("detail",sa.JSON(),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False))
 for t,cs in {"change_requests":("company_id","branch_id","site_id","change_number","change_type","risk_level","planned_release_date","status"),"change_audit_events":("company_id","branch_id","site_id","action","occurred_at")}.items():
  for c in cs:op.create_index(f"ix_{t}_{c}",t,[c])
def downgrade():
 for t in ("change_audit_events","change_requests"):
  for i in [r["name"] for r in sa.inspect(op.get_bind()).get_indexes(t)]:op.drop_index(i,table_name=t)
  op.drop_table(t)
