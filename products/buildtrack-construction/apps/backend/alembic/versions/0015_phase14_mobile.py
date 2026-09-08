"""Phase 14 mobile offline field capture.

Revision ID: 0015_phase14_mobile
Revises: 0014_phase13_assurance
"""
from alembic import op
import sqlalchemy as sa
revision="0015_phase14_mobile"
down_revision="0014_phase13_assurance"
branch_labels=None
depends_on=None
def upgrade()->None:
 op.create_table("offline_field_submissions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("company_id",sa.Integer(),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",sa.Integer(),sa.ForeignKey("branches.id",ondelete="RESTRICT"),nullable=False),sa.Column("site_id",sa.Integer(),sa.ForeignKey("sites.id",ondelete="RESTRICT"),nullable=False),sa.Column("project_id",sa.Integer(),sa.ForeignKey("projects.id",ondelete="CASCADE"),nullable=False),sa.Column("device_id",sa.String(120),nullable=False),sa.Column("client_submission_id",sa.String(120),nullable=False),sa.Column("submission_type",sa.String(48),nullable=False),sa.Column("captured_at",sa.DateTime(timezone=True),nullable=False),sa.Column("payload",sa.JSON(),nullable=False),sa.Column("status",sa.String(24),nullable=False),sa.Column("reviewer_note",sa.Text()),sa.Column("received_by",sa.String(255),nullable=False),sa.Column("received_at",sa.DateTime(timezone=True),nullable=False),sa.Column("reviewed_by",sa.String(255)),sa.Column("reviewed_at",sa.DateTime(timezone=True)),sa.UniqueConstraint("company_id","device_id","client_submission_id",name="uq_offline_submission_device_client"))
 for column in ("company_id","branch_id","site_id","project_id","device_id","submission_type","captured_at","status"):op.create_index(f"ix_offline_field_submissions_{column}","offline_field_submissions",[column])
def downgrade()->None:
 for column in ("status","captured_at","submission_type","device_id","project_id","site_id","branch_id","company_id"):op.drop_index(f"ix_offline_field_submissions_{column}",table_name="offline_field_submissions")
 op.drop_table("offline_field_submissions")
