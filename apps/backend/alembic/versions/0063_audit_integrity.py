"""tamper-evident append-only audit ledger

Revision ID: 0063_audit_integrity
Revises: 0062_mail_backup_immutability
"""

from alembic import op
import sqlalchemy as sa

revision = "0063_audit_integrity"
down_revision = "0062_mail_backup_immutability"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("audit_logs", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("event_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_logs_event_hash", "audit_logs", ["event_hash"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        op.execute(
            r"""
            CREATE OR REPLACE FUNCTION ithute_audit_hash_insert()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
              v_prev text;
              v_scope text;
              v_payload text;
            BEGIN
              v_scope := COALESCE(NEW.tenant_id::text, 'platform');
              PERFORM pg_advisory_xact_lock(hashtext('ithute-audit:' || v_scope));

              SELECT event_hash INTO v_prev
              FROM audit_logs
              WHERE COALESCE(tenant_id::text, 'platform') = v_scope
              ORDER BY created_at DESC NULLS LAST, id DESC
              LIMIT 1;

              NEW.prev_hash := v_prev;
              v_payload := concat_ws(
                chr(31),
                COALESCE(v_prev, ''),
                NEW.id::text,
                COALESCE(NEW.tenant_id::text, ''),
                COALESCE(NEW.actor_user_id::text, ''),
                COALESCE(NEW.action, ''),
                COALESCE(NEW.resource_type, ''),
                COALESCE(NEW.resource_id, ''),
                COALESCE(NEW.metadata_json, '')
              );
              NEW.event_hash := encode(digest(v_payload, 'sha256'), 'hex');
              RETURN NEW;
            END
            $$;
            """
        )
        op.execute(
            r"""
            CREATE OR REPLACE FUNCTION ithute_audit_block_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
              RAISE EXCEPTION 'audit_logs is append-only';
            END
            $$;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_audit_hash_insert
            BEFORE INSERT ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION ithute_audit_hash_insert()
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_audit_append_only
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION ithute_audit_block_mutation()
            """
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_append_only ON audit_logs")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_hash_insert ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS ithute_audit_block_mutation()")
        op.execute("DROP FUNCTION IF EXISTS ithute_audit_hash_insert()")
    op.drop_index("ix_audit_logs_event_hash", table_name="audit_logs")
    op.drop_column("audit_logs", "event_hash")
    op.drop_column("audit_logs", "prev_hash")
