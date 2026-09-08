"""Phase 30 client portal and controlled external sharing."""
from alembic import op
import sqlalchemy as sa
revision="0031_phase30_client_portal"
down_revision="0030_phase29_tools"
branch_labels=None
depends_on=None
def upgrade():
 op.create_table("client_share_packs",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("project_id",sa.Integer(),sa.ForeignKey("projects.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="RESTRICT"),nullable=False),sa.Column("pack_number",sa.String(80),nullable=False),sa.Column("title",sa.String(300),nullable=False),sa.Column("client_name",sa.String(240),nullable=False),sa.Column("message",sa.Text()),sa.Column("document_id",sa.Integer(),sa.ForeignKey("documents.id",ondelete="RESTRICT"),nullable=False),sa.Column("expiry_date",sa.Date(),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.Column("token_hash",sa.String(64)),sa.Column("prepared_by",sa.String(255),nullable=False),sa.Column("submitted_at",sa.DateTime(timezone=True)),sa.Column("published_by",sa.String(255)),sa.Column("published_at",sa.DateTime(timezone=True)),sa.Column("revoked_by",sa.String(255)),sa.Column("revoked_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("company_id","pack_number",name="uq_client_share_pack_number"),sa.UniqueConstraint("token_hash",name="uq_client_share_token"))
 op.create_table("client_portal_audit_events",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="SET NULL")),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="SET NULL")),sa.Column("actor",sa.String(255),nullable=False),sa.Column("action",sa.String(120),nullable=False),sa.Column("entity_type",sa.String(80),nullable=False),sa.Column("entity_id",sa.String(100),nullable=False),sa.Column("detail",sa.JSON(),nullable=False),sa.Column("occurred_at",sa.DateTime(timezone=True),nullable=False))
 for t,cs in {"client_share_packs":("company_id","project_id","branch_id","site_id","pack_number","document_id","expiry_date","status","token_hash"),"client_portal_audit_events":("company_id","branch_id","site_id","action","occurred_at")}.items():
  for c in cs:op.create_index(f"ix_{t}_{c}",t,[c])
def downgrade():
 for t in ("client_portal_audit_events","client_share_packs"):
  for r in sa.inspect(op.get_bind()).get_indexes(t):op.drop_index(r["name"],table_name=t)
  op.drop_table(t)
