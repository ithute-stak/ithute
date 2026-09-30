from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]


def test_backup_claim_carries_application_username():
    source = (BACKEND / "app/api/v1/hosting_database_backups.py").read_text()
    assert '"username": database.username' in source
    assert '"database_name": database.database_name' in source
    assert '"engine": database.engine' in source


def test_v4_postgres_keeps_hosting_admin_as_database_owner():
    source = (ROOT / "infrastructure/hosting-agent/agent_v4.py").read_text()
    assert "base.postgres_operation = postgres_operation_v4" in source
    assert 'f"--owner={username}"' not in source
    assert "owner != base.POSTGRES_ADMIN_USER" in source
    assert '"--force"' in source


def test_v4_postgres_revokes_shared_cluster_defaults():
    source = (ROOT / "infrastructure/hosting-agent/agent_v4.py").read_text()
    assert "REVOKE CONNECT, TEMPORARY ON DATABASE" in source
    assert "GRANT CONNECT, TEMPORARY ON DATABASE" in source
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in source
    assert "GRANT USAGE, CREATE ON SCHEMA public" in source


def test_v4_backup_and_restore_assume_customer_role():
    source = (ROOT / "infrastructure/hosting-agent/agent_v4.py").read_text()
    assert source.count('"--role", username') >= 2
    assert "_postgres_backup(database_name, username, temporary)" in source
    assert "_postgres_restore(database_name, username, final)" in source
