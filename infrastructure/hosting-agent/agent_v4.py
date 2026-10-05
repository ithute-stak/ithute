#!/usr/bin/env python3
"""Ithute hosting-node agent v4 with managed database backup/restore.

One host process continues to own privileged runtime/database operations. This
entrypoint extends v3 with database-native backup and restore jobs stored under
a dedicated scoped backup root.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import pathlib
import re
import signal
import shutil
import subprocess
import tempfile
import time
from typing import Any

import agent_v3 as runtime
import backup_remote
from network_policy import choose_project_subnet, parse_existing_subnets, parse_pool

base = runtime.base
AGENT_VERSION = "ithute-hosting-agent/4"
base.AGENT_VERSION = AGENT_VERSION
BACKUP_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_DATABASE_BACKUP_ROOT", "/var/lib/ithute-hosting/database-backups"))
PG_DUMP = os.getenv("ITHUTE_HOSTING_PG_DUMP", "pg_dump")
PG_RESTORE = os.getenv("ITHUTE_HOSTING_PG_RESTORE", "pg_restore")
MYSQLDUMP = os.getenv("ITHUTE_HOSTING_MYSQLDUMP", "mysqldump")
MAX_BACKUP_BYTES = int(os.getenv("ITHUTE_HOSTING_DATABASE_BACKUP_MAX_BYTES", str(20 * 1024 * 1024 * 1024)))
POSTGRES_REPLICATION_MODE = os.getenv("ITHUTE_HOSTING_POSTGRES_REPLICATION_MODE", "disabled").strip().lower()
POSTGRES_DATA_DIR = os.getenv("ITHUTE_HOSTING_POSTGRES_DATA_DIR", "").strip()
POSTGRES_SERVICE = os.getenv("ITHUTE_HOSTING_POSTGRES_SERVICE", "").strip()
POSTGRES_REPLICATION_DEDICATED = os.getenv("ITHUTE_HOSTING_POSTGRES_REPLICATION_DEDICATED", "false").lower() == "true"
PG_BASEBACKUP = os.getenv("ITHUTE_HOSTING_PG_BASEBACKUP", "pg_basebackup").strip()
PG_CTL = os.getenv("ITHUTE_HOSTING_PG_CTL", "pg_ctl").strip()
PG_REWIND = os.getenv("ITHUTE_HOSTING_PG_REWIND", "pg_rewind").strip()
PG_CONTROLDATA = os.getenv("ITHUTE_HOSTING_PG_CONTROLDATA", "pg_controldata").strip()
POSTGRES_REPLICATION_USER = os.getenv("ITHUTE_HOSTING_POSTGRES_REPLICATION_USER", "").strip()
POSTGRES_REPLICATION_PASSWORD = os.getenv("ITHUTE_HOSTING_POSTGRES_REPLICATION_PASSWORD", "")
_SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")
if POSTGRES_REPLICATION_MODE not in {"disabled", "physical_cluster"}:
    raise RuntimeError("ITHUTE_HOSTING_POSTGRES_REPLICATION_MODE must be disabled or physical_cluster")
HOSTED_NETWORK_PREFIX = int(os.getenv("ITHUTE_HOSTING_NETWORK_PREFIX", "28"))
HOSTED_NETWORK_POOL = parse_pool(os.getenv("ITHUTE_HOSTING_NETWORK_POOL", "10.240.0.0/12"), HOSTED_NETWORK_PREFIX)


def _existing_network_subnets() -> list[ipaddress.IPv4Network]:
    ids = base.docker("network", "ls", "-q").stdout.splitlines()
    values: list[str] = []
    for network_id in ids:
        network_id = network_id.strip()
        if not network_id:
            continue
        inspected = base.docker(
            "network", "inspect", network_id,
            "--format", "{{range .IPAM.Config}}{{println .Subnet}}{{end}}",
            check=False,
        )
        if inspected.returncode == 0:
            values.extend(inspected.stdout.splitlines())
    return parse_existing_subnets(values)


def ensure_hosted_network(name: str, project_id: str) -> None:
    if base.exists("network", name):
        existing = base.docker(
            "network", "inspect", name,
            "--format", "{{range .IPAM.Config}}{{println .Subnet}}{{end}}",
        ).stdout.splitlines()
        parsed = parse_existing_subnets(existing)
        if len(parsed) != 1 or not parsed[0].subnet_of(HOSTED_NETWORK_POOL):
            raise RuntimeError(
                f"Existing project network {name} is outside the reserved Ithute pool {HOSTED_NETWORK_POOL}; "
                "remove the stopped legacy project network before redeploying"
            )
        return

    candidate = choose_project_subnet(
        HOSTED_NETWORK_POOL,
        HOSTED_NETWORK_PREFIX,
        project_id,
        _existing_network_subnets(),
    )
    base.docker(
        "network", "create",
        "--driver", "bridge",
        "--subnet", str(candidate),
        "--label", "ithute.hosted=true",
        "--label", f"ithute.project={project_id}",
        name,
    )


# base.activate resolves ensure_network from the base module globals at runtime.
# Replacing the module attribute here upgrades every deployment handled by v4
# without duplicating the mature activation/rollback implementation.
base.ensure_network = ensure_hosted_network


def postgres_physical_replication_capabilities() -> dict[str, Any]:
    configured = POSTGRES_REPLICATION_MODE == "physical_cluster"
    data_dir_ok = bool(POSTGRES_DATA_DIR) and pathlib.Path(POSTGRES_DATA_DIR).is_absolute()
    service_ok = bool(POSTGRES_SERVICE) and bool(_SERVICE_RE.fullmatch(POSTGRES_SERVICE))
    basebackup_available = shutil.which(PG_BASEBACKUP) is not None
    pg_ctl_available = shutil.which(PG_CTL) is not None
    pg_rewind_available = shutil.which(PG_REWIND) is not None
    pg_controldata_available = shutil.which(PG_CONTROLDATA) is not None
    replication_credentials_configured = (
        bool(base.DB_USER_RE.fullmatch(POSTGRES_REPLICATION_USER))
        and 20 <= len(POSTGRES_REPLICATION_PASSWORD) <= 256
    )
    supported = (
        configured
        and POSTGRES_REPLICATION_DEDICATED
        and data_dir_ok
        and service_ok
        and basebackup_available
        and pg_ctl_available
        and replication_credentials_configured
    )
    result: dict[str, Any] = {
        "mode": POSTGRES_REPLICATION_MODE,
        "supported": supported,
        "promotion_requires_source_fencing": True,
        "dedicated_cluster": POSTGRES_REPLICATION_DEDICATED,
        "data_dir_configured": data_dir_ok,
        "service_configured": service_ok,
        "pg_basebackup_available": basebackup_available,
        "pg_ctl_available": pg_ctl_available,
        "pg_rewind_available": pg_rewind_available,
        "pg_controldata_available": pg_controldata_available,
        "replication_credentials_configured": replication_credentials_configured,
    }
    if configured:
        try:
            recovery, receive_lsn, replay_lsn, backlog_bytes, replay_age, receiver_status = base.psql(
                "SELECT pg_is_in_recovery()::text || '|' || "
                "COALESCE(pg_last_wal_receive_lsn()::text,'') || '|' || "
                "COALESCE(pg_last_wal_replay_lsn()::text,'') || '|' || "
                "COALESCE(pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn())::bigint::text,'') || '|' || "
                "COALESCE(EXTRACT(EPOCH FROM (clock_timestamp()-pg_last_xact_replay_timestamp()))::text,'') || '|' || "
                "COALESCE((SELECT status FROM pg_stat_wal_receiver LIMIT 1),'')"
            ).split("|", 5)
            result["in_recovery"] = recovery == "true"
            result["receive_lsn"] = receive_lsn or None
            result["replay_lsn"] = replay_lsn or None
            result["replay_backlog_bytes"] = int(backlog_bytes) if backlog_bytes else None
            result["replay_age_seconds"] = float(replay_age) if replay_age else None
            result["wal_receiver_status"] = receiver_status or None
            result["wal_receiver_streaming"] = receiver_status == "streaming"
            if result["in_recovery"] is False:
                sync_commit = base.psql("SHOW synchronous_commit").strip().lower()
                sync_names = base.psql("SHOW synchronous_standby_names").strip()
                streaming, synchronous = base.psql(
                    "SELECT count(*) FILTER (WHERE state='streaming')::text || '|' || "
                    "count(*) FILTER (WHERE state='streaming' AND sync_state IN ('sync','quorum'))::text "
                    "FROM pg_stat_replication"
                ).split("|", 1)
                result["primary_synchronous_commit"] = sync_commit
                result["primary_synchronous_standby_names"] = sync_names
                result["primary_streaming_standbys"] = int(streaming)
                result["primary_sync_standbys"] = int(synchronous)
            try:
                wal_log_hints = base.psql("SHOW wal_log_hints").strip().lower() == "on"
                data_checksums = base.psql("SHOW data_checksums").strip().lower() == "on"
                result["wal_log_hints"] = wal_log_hints
                result["data_checksums"] = data_checksums
                result["pg_rewind_safe_prerequisites"] = bool(
                    pg_rewind_available and (wal_log_hints or data_checksums)
                )
            except Exception as exc:
                result["pg_rewind_prerequisite_error"] = str(exc)[:300]
                result["pg_rewind_safe_prerequisites"] = False
        except Exception as exc:
            result["status_error"] = str(exc)[:300]
    return result


def postgres_bootstrap_physical_replica(
    *,
    source_host: str,
    source_port: int,
    replication_user: str,
    replication_password: str,
) -> dict[str, Any]:
    capabilities = postgres_physical_replication_capabilities()
    if not capabilities.get("supported"):
        raise RuntimeError("PostgreSQL physical replication is not safely configured on this hosting node")
    if not source_host or any(ch.isspace() for ch in source_host) or "\x00" in source_host:
        raise RuntimeError("PostgreSQL replication source host is invalid")
    if not 1 <= int(source_port) <= 65535:
        raise RuntimeError("PostgreSQL replication source port is invalid")
    if not base.DB_USER_RE.fullmatch(replication_user):
        raise RuntimeError("PostgreSQL replication user is invalid")
    if len(replication_password) < 20 or len(replication_password) > 256:
        raise RuntimeError("PostgreSQL replication password is invalid")

    data_dir = pathlib.Path(POSTGRES_DATA_DIR)
    if not data_dir.is_absolute() or data_dir == pathlib.Path("/"):
        raise RuntimeError("PostgreSQL replication data directory is unsafe")
    data_dir.mkdir(parents=True, exist_ok=True)
    if any(data_dir.iterdir()):
        raise RuntimeError("Refusing pg_basebackup into a non-empty PostgreSQL data directory")

    base.command(["systemctl", "stop", POSTGRES_SERVICE], timeout=120)
    try:
        base.command(
            [
                PG_BASEBACKUP,
                "--pgdata", str(data_dir),
                "--host", source_host,
                "--port", str(source_port),
                "--username", replication_user,
                "--wal-method=stream",
                "--write-recovery-conf",
                "--checkpoint=fast",
                "--no-password",
            ],
            timeout=7200,
            extra_env={"PGPASSWORD": replication_password},
        )
    except Exception:
        # Do not start a partially initialized standby.
        raise

    base.command(["systemctl", "start", POSTGRES_SERVICE], timeout=120)
    recovery = base.psql("SELECT pg_is_in_recovery()::text")
    if recovery != "true":
        base.command(["systemctl", "stop", POSTGRES_SERVICE], check=False, timeout=120)
        raise RuntimeError("Bootstrapped PostgreSQL cluster did not enter standby recovery mode")
    return {"bootstrapped": True, "in_recovery": True, "data_dir": str(data_dir)}


def _postgres_checksums_enabled_offline() -> bool:
    if shutil.which(PG_CONTROLDATA) is None:
        return False
    data_dir = _postgres_data_dir()
    result = base.command(
        [PG_CONTROLDATA, str(data_dir)],
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        return False
    for line in result.stdout.splitlines():
        if line.lower().startswith("data page checksum version:"):
            try:
                return int(line.split(":", 1)[1].strip()) > 0
            except ValueError:
                return False
    return False


def _postgres_data_dir() -> pathlib.Path:
    data_dir = pathlib.Path(POSTGRES_DATA_DIR)
    if not data_dir.is_absolute() or data_dir == pathlib.Path("/") or len(data_dir.parts) < 4:
        raise RuntimeError("PostgreSQL replication data directory is unsafe")
    return data_dir


def _reset_postgres_data_dir() -> pathlib.Path:
    if not POSTGRES_REPLICATION_DEDICATED:
        raise RuntimeError("Refusing to reset PostgreSQL data on a non-dedicated cluster")
    data_dir = _postgres_data_dir()
    base.command(["systemctl", "stop", POSTGRES_SERVICE], timeout=120)
    data_dir.mkdir(parents=True, exist_ok=True)
    for child in data_dir.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            raise RuntimeError(f"Unsupported PostgreSQL data-directory entry: {child.name}")
    return data_dir


def postgres_repair_physical_replica(
    *,
    source_host: str,
    source_port: int,
    method: str,
) -> dict[str, Any]:
    capabilities = postgres_physical_replication_capabilities()
    if not capabilities.get("supported"):
        raise RuntimeError("PostgreSQL physical replication is not safely configured on this hosting node")
    if not source_host or any(ch.isspace() for ch in source_host) or "\x00" in source_host:
        raise RuntimeError("PostgreSQL repair source host is invalid")
    if not 1 <= int(source_port) <= 65535:
        raise RuntimeError("PostgreSQL repair source port is invalid")
    if method not in {"rewind", "basebackup"}:
        raise RuntimeError("Unsupported PostgreSQL topology repair method")
    if not base.DB_USER_RE.fullmatch(POSTGRES_REPLICATION_USER):
        raise RuntimeError("PostgreSQL replication user is not configured")
    if not 20 <= len(POSTGRES_REPLICATION_PASSWORD) <= 256:
        raise RuntimeError("PostgreSQL replication password is not configured")

    data_dir = _postgres_data_dir()
    env = {"PGPASSWORD": POSTGRES_REPLICATION_PASSWORD}
    if method == "rewind":
        if not capabilities.get("pg_rewind_available"):
            raise RuntimeError("pg_rewind is unavailable")
        if not _postgres_checksums_enabled_offline():
            raise RuntimeError("pg_rewind requires locally verified PostgreSQL page checksums; use basebackup")
        base.command(["systemctl", "stop", POSTGRES_SERVICE], timeout=120)
        conninfo = (
            f"host={source_host} port={int(source_port)} "
            f"user={POSTGRES_REPLICATION_USER} dbname={base.POSTGRES_ADMIN_DATABASE}"
        )
        base.command(
            [
                PG_REWIND,
                "--target-pgdata", str(data_dir),
                "--source-server", conninfo,
                "--write-recovery-conf",
                "--progress",
            ],
            timeout=7200,
            extra_env=env,
        )
    else:
        data_dir = _reset_postgres_data_dir()
        base.command(
            [
                PG_BASEBACKUP,
                "--pgdata", str(data_dir),
                "--host", source_host,
                "--port", str(source_port),
                "--username", POSTGRES_REPLICATION_USER,
                "--wal-method=stream",
                "--write-recovery-conf",
                "--checkpoint=fast",
                "--no-password",
            ],
            timeout=7200,
            extra_env=env,
        )

    base.command(["systemctl", "start", POSTGRES_SERVICE], timeout=120)
    recovery = base.psql("SELECT pg_is_in_recovery()::text")
    if recovery != "true":
        base.command(["systemctl", "stop", POSTGRES_SERVICE], check=False, timeout=120)
        raise RuntimeError("Repaired PostgreSQL node did not enter standby recovery mode")
    receiver = base.psql(
        "SELECT COALESCE((SELECT status FROM pg_stat_wal_receiver LIMIT 1),'')"
    ).strip()
    if receiver != "streaming":
        raise RuntimeError("Repaired PostgreSQL node is not streaming WAL from the new primary")
    return {"repaired": True, "method": method, "in_recovery": True, "wal_receiver_status": receiver}


def postgres_promote_physical_replica(*, source_fencing_confirmed: bool) -> dict[str, Any]:
    capabilities = postgres_physical_replication_capabilities()
    if not capabilities.get("supported"):
        raise RuntimeError("PostgreSQL physical replication is not safely configured on this hosting node")
    if not source_fencing_confirmed:
        raise RuntimeError("Refusing PostgreSQL promotion without confirmed old-primary fencing")
    if capabilities.get("in_recovery") is not True:
        raise RuntimeError("Refusing PostgreSQL promotion because this node is not a standby")
    promoted = base.psql("SELECT pg_promote(wait_seconds => 60)::text")
    if promoted != "true":
        raise RuntimeError("PostgreSQL did not confirm standby promotion")
    if base.psql("SELECT pg_is_in_recovery()::text") != "false":
        raise RuntimeError("PostgreSQL promotion returned but server remains in recovery")
    return {"promoted": True, "in_recovery": False}


def _psql_database(database_name: str, sql: str) -> str:
    args = [
        base.PSQL,
        *base.postgres_connection_args(),
        "--dbname", database_name,
        "-v", "ON_ERROR_STOP=1",
        "-Atqc", sql,
    ]
    return base.command(args, timeout=60, extra_env=base.postgres_environment()).stdout.strip()


def _postgres_database_owner(database_name: str) -> str | None:
    value = base.psql(
        "SELECT pg_get_userbyid(datdba) FROM pg_database "
        f"WHERE datname={base.sql_literal(database_name)}"
    ).strip()
    return value or None


def postgres_operation_v4(work: dict[str, Any]) -> tuple[str, int, str | None]:
    """Provision PostgreSQL without requiring a superuser hosting admin.

    The hosting admin owns each database so CREATEDB is sufficient for create/drop.
    The customer login receives only database CONNECT/TEMP and CREATE/USAGE on the
    public schema. Objects created by the application remain owned by the customer
    role; backup/restore SET ROLE to that customer role.
    """
    _, operation, _, database_name, username = base.validate_database_work(work)
    password = str(work["password"])

    if not base.DB_USER_RE.fullmatch(base.POSTGRES_ADMIN_USER):
        raise RuntimeError("PostgreSQL hosting admin username is not a safe role identifier")

    if operation == "provision":
        if base.postgres_role_exists(username):
            base.psql(f"ALTER ROLE {username} LOGIN PASSWORD {base.sql_literal(password)}")
        else:
            base.psql(f"CREATE ROLE {username} LOGIN PASSWORD {base.sql_literal(password)}")

        if not base.postgres_database_exists(database_name):
            base.command(
                [
                    base.CREATEDB,
                    *base.postgres_connection_args(),
                    f"--maintenance-db={base.POSTGRES_ADMIN_DATABASE}",
                    database_name,
                ],
                timeout=120,
                extra_env=base.postgres_environment(),
            )
        else:
            owner = _postgres_database_owner(database_name)
            if owner != base.POSTGRES_ADMIN_USER:
                raise RuntimeError(
                    "Existing PostgreSQL database uses legacy customer ownership; "
                    "migrate its owner to the configured Ithute hosting admin before retrying"
                )

        base.psql(
            f"REVOKE CONNECT, TEMPORARY ON DATABASE {database_name} FROM PUBLIC; "
            f"GRANT CONNECT, TEMPORARY ON DATABASE {database_name} TO {username}"
        )
        _psql_database(
            database_name,
            f"REVOKE CREATE ON SCHEMA public FROM PUBLIC; "
            f"GRANT USAGE, CREATE ON SCHEMA public TO {username}",
        )
    elif operation == "rotate":
        if not base.postgres_role_exists(username):
            raise RuntimeError("PostgreSQL role no longer exists")
        base.psql(f"ALTER ROLE {username} LOGIN PASSWORD {base.sql_literal(password)}")
    elif operation == "suspend":
        base.psql(f"ALTER ROLE {username} NOLOGIN")
    elif operation == "resume":
        base.psql(f"ALTER ROLE {username} LOGIN")
    elif operation == "delete":
        owner = _postgres_database_owner(database_name)
        if owner is not None and owner != base.POSTGRES_ADMIN_USER:
            raise RuntimeError("Refusing to drop PostgreSQL database not owned by the Ithute hosting admin")
        base.command(
            [
                base.DROPDB,
                *base.postgres_connection_args(),
                f"--maintenance-db={base.POSTGRES_ADMIN_DATABASE}",
                "--if-exists",
                "--force",
                database_name,
            ],
            timeout=120,
            extra_env=base.postgres_environment(),
        )
        base.psql(f"DROP ROLE IF EXISTS {username}")

    version = base.psql("SHOW server_version") if operation != "delete" else None
    return base.POSTGRES_APP_HOST, base.POSTGRES_APP_PORT, version


base.postgres_operation = postgres_operation_v4


def _safe_storage_path(storage_key: str) -> pathlib.Path:
    if not storage_key or "\\" in storage_key or "\x00" in storage_key:
        raise RuntimeError("Database backup contains an invalid storage key")
    relative = pathlib.PurePosixPath(storage_key)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise RuntimeError("Database backup contains an unsafe storage key")
    target = (BACKUP_ROOT / pathlib.Path(*relative.parts)).resolve()
    root = BACKUP_ROOT.resolve()
    if target != root and root not in target.parents:
        raise RuntimeError("Database backup storage key escapes the backup root")
    return target


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _backup_matches(path: pathlib.Path, expected_sha: str, expected_size: int) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    actual_size = path.stat().st_size
    if actual_size != expected_size or actual_size <= 0 or actual_size > MAX_BACKUP_BYTES:
        return False
    return _sha256(path) == expected_sha


def _ensure_verified_backup_local(storage_key: str, path: pathlib.Path, expected_sha: str, expected_size: int) -> None:
    if _backup_matches(path, expected_sha, expected_size):
        return
    # Never restore from a stale/corrupt local payload. Remove it first, then
    # rehydrate from the configured off-node object store when available.
    path.unlink(missing_ok=True)
    hydrated = backup_remote.hydrate(storage_key, path)
    if not hydrated:
        raise RuntimeError("Verified database backup is unavailable locally and no off-node remote is configured")
    if not _backup_matches(path, expected_sha, expected_size):
        path.unlink(missing_ok=True)
        raise RuntimeError("Rehydrated database backup failed control-plane size/SHA-256 verification")


def claim_postgres_topology_repair() -> dict[str, Any] | None:
    result = base.api("/hosting/agent/postgres-topology-repairs/claim")
    work = result.get("repair")
    return work if isinstance(work, dict) else None


def report_postgres_topology_repair(
    repair_id: str,
    token: str,
    success: bool,
    *,
    method_used: str | None = None,
    receive_lsn: str | None = None,
    replay_lsn: str | None = None,
    replay_backlog_bytes: int | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    return base.api(
        f"/hosting/agent/postgres-topology-repairs/{repair_id}/status",
        {
            "token": token,
            "success": success,
            "method_used": method_used,
            "receive_lsn": receive_lsn,
            "replay_lsn": replay_lsn,
            "replay_backlog_bytes": replay_backlog_bytes,
            "message": message,
        },
    )


def process_postgres_topology_repair(work: dict[str, Any]) -> None:
    repair_id = str(work.get("id") or "")
    token = str(work.get("token") or "")
    method = str(work.get("method") or "")
    source = work.get("source")
    if not repair_id or len(token) < 20 or method not in {"rewind", "basebackup"} or not isinstance(source, dict):
        raise RuntimeError("PostgreSQL topology repair job is incomplete")

    source_host = str(source.get("host") or "")
    source_port = int(source.get("port") or 0)
    try:
        postgres_repair_physical_replica(
            source_host=source_host,
            source_port=source_port,
            method=method,
        )
        receive_lsn, replay_lsn, backlog = base.psql(
            "SELECT COALESCE(pg_last_wal_receive_lsn()::text,'') || '|' || "
            "COALESCE(pg_last_wal_replay_lsn()::text,'') || '|' || "
            "COALESCE(pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn())::bigint::text,'')"
        ).split("|", 2)
        if not receive_lsn or not replay_lsn or not backlog:
            raise RuntimeError("Repaired PostgreSQL node did not expose verified WAL positions")
        report_postgres_topology_repair(
            repair_id,
            token,
            True,
            method_used=method,
            receive_lsn=receive_lsn,
            replay_lsn=replay_lsn,
            replay_backlog_bytes=int(backlog),
            message=f"PostgreSQL topology repaired with {method}",
        )
    except Exception as exc:
        error = str(exc)[:1900]
        base.log(f"postgres topology repair {repair_id} failed: {error}")
        try:
            report_postgres_topology_repair(
                repair_id,
                token,
                False,
                method_used=method,
                message=error,
            )
        except Exception as report_exc:
            base.log(f"could not report postgres topology repair failure: {report_exc}")


def claim_postgres_group_failover() -> dict[str, Any] | None:
    result = base.api("/hosting/agent/postgres-group-failovers/claim")
    work = result.get("failover")
    return work if isinstance(work, dict) else None


def report_postgres_group_failover(
    attempt_id: str,
    token: str,
    success: bool,
    *,
    message: str | None = None,
) -> dict[str, Any]:
    return base.api(
        f"/hosting/agent/postgres-group-failovers/{attempt_id}/status",
        {"token": token, "success": success, "message": message},
    )


def process_postgres_group_failover(work: dict[str, Any]) -> None:
    attempt_id = str(work.get("id") or "")
    action = str(work.get("action") or "")
    token = str(work.get("token") or "")
    if not attempt_id or len(token) < 20:
        raise RuntimeError("PostgreSQL group failover job is incomplete")

    try:
        capabilities = postgres_physical_replication_capabilities()
        if not capabilities.get("supported"):
            raise RuntimeError("Dedicated PostgreSQL physical replication capability is unavailable")

        if action == "fence_source":
            if capabilities.get("in_recovery") is True:
                raise RuntimeError("Refusing to fence a PostgreSQL standby as the old group primary")
            base.command(["systemctl", "stop", POSTGRES_SERVICE], timeout=120)
            active = base.command(["systemctl", "is-active", POSTGRES_SERVICE], check=False, timeout=30)
            if active.returncode == 0:
                raise RuntimeError("PostgreSQL group primary remained active after fencing request")
            report_postgres_group_failover(
                attempt_id,
                token,
                True,
                message="Old PostgreSQL group primary stopped and verified inactive",
            )
            return

        if action == "promote_target":
            if work.get("source_fencing_confirmed") is not True:
                raise RuntimeError("Control plane did not confirm PostgreSQL group source fencing")
            postgres_promote_physical_replica(source_fencing_confirmed=True)
            report_postgres_group_failover(
                attempt_id,
                token,
                True,
                message="PostgreSQL group standby promoted and verified out of recovery",
            )
            return

        raise RuntimeError("Unknown PostgreSQL group failover action")
    except Exception as exc:
        error = str(exc)[:1900]
        base.log(f"postgres group failover {attempt_id} failed: {error}")
        try:
            report_postgres_group_failover(attempt_id, token, False, message=error)
        except Exception as report_exc:
            base.log(f"could not report postgres group failover failure: {report_exc}")


def claim_database_failover() -> dict[str, Any] | None:
    result = base.api("/hosting/agent/database-failovers/claim")
    work = result.get("failover")
    return work if isinstance(work, dict) else None


def report_database_failover(
    attempt_id: str,
    token: str,
    success: bool,
    *,
    message: str | None = None,
) -> dict[str, Any]:
    return base.api(
        f"/hosting/agent/database-failovers/{attempt_id}/status",
        {"token": token, "success": success, "message": message},
    )


def process_database_failover(work: dict[str, Any]) -> None:
    attempt_id = str(work.get("id") or "")
    action = str(work.get("action") or "")
    token = str(work.get("token") or "")
    if not attempt_id or len(token) < 20:
        raise RuntimeError("Database failover job is incomplete")

    try:
        capabilities = postgres_physical_replication_capabilities()
        if not capabilities.get("supported"):
            raise RuntimeError("Dedicated PostgreSQL physical replication capability is unavailable")

        if action == "fence_source":
            if capabilities.get("in_recovery") is True:
                raise RuntimeError("Refusing to fence a PostgreSQL standby as the old primary")
            base.command(["systemctl", "stop", POSTGRES_SERVICE], timeout=120)
            active = base.command(["systemctl", "is-active", POSTGRES_SERVICE], check=False, timeout=30)
            if active.returncode == 0:
                raise RuntimeError("PostgreSQL source service remained active after fencing request")
            report_database_failover(attempt_id, token, True, message="Old primary PostgreSQL service stopped and verified inactive")
            return

        if action == "promote_target":
            if work.get("source_fencing_confirmed") is not True:
                raise RuntimeError("Control plane did not confirm source fencing")
            postgres_promote_physical_replica(source_fencing_confirmed=True)
            report_database_failover(attempt_id, token, True, message="PostgreSQL standby promoted and verified out of recovery")
            return

        raise RuntimeError("Unknown database failover action")
    except Exception as exc:
        error = str(exc)[:1900]
        base.log(f"database failover {attempt_id} failed: {error}")
        try:
            report_database_failover(attempt_id, token, False, message=error)
        except Exception as report_exc:
            base.log(f"could not report database failover failure: {report_exc}")


def claim_database_backup() -> dict[str, Any] | None:
    result = base.api("/hosting/agent/database-backups/claim")
    work = result.get("backup")
    return work if isinstance(work, dict) else None


def report_database_backup(
    backup_id: str,
    success: bool,
    *,
    sha256: str | None = None,
    size_bytes: int | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    return base.api(
        f"/hosting/agent/database-backups/{backup_id}/status",
        {"success": success, "sha256": sha256, "size_bytes": size_bytes, "message": message},
    )


def _validate_work(work: dict[str, Any]) -> tuple[str, str, str, str, str, pathlib.Path]:
    backup_id = str(work.get("id") or "")
    operation = str(work.get("operation") or "")
    database = work.get("database")
    if not backup_id or operation not in {"backup", "restore"} or not isinstance(database, dict):
        raise RuntimeError("Database backup job is incomplete")
    engine = str(database.get("engine") or "")
    database_name = str(database.get("database_name") or "")
    username = str(database.get("username") or "")
    if engine not in {"postgresql", "mysql"}:
        raise RuntimeError("Database backup job has an unsupported engine")
    if not base.DB_IDENT_RE.fullmatch(database_name) or not base.DB_USER_RE.fullmatch(username):
        raise RuntimeError("Database backup job contains an invalid database identifier")
    if operation == "restore" and str(database.get("status") or "") != "suspended":
        raise RuntimeError("Database must remain suspended during restore")
    return backup_id, operation, engine, database_name, username, _safe_storage_path(str(work.get("storage_key") or ""))


def _run_to_file(args: list[str], path: pathlib.Path, *, env: dict[str, str], timeout: int = 3600) -> None:
    with path.open("wb") as output:
        result = subprocess.run(args, stdout=output, stderr=subprocess.PIPE, env={**os.environ, **env}, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"database dump command failed: {detail}")


def _run_from_file(args: list[str], path: pathlib.Path, *, env: dict[str, str], timeout: int = 3600) -> None:
    with path.open("rb") as source:
        result = subprocess.run(args, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, **env}, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"database restore command failed: {detail}")


def _postgres_backup(database_name: str, username: str, temporary: pathlib.Path) -> None:
    args = [
        PG_DUMP,
        *base.postgres_connection_args(),
        "--dbname", database_name,
        "--role", username,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file", str(temporary),
    ]
    result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env={**os.environ, **base.postgres_environment()}, timeout=3600, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.decode('utf-8', errors='replace')[-2000:]}")


def _postgres_restore(database_name: str, username: str, backup: pathlib.Path) -> None:
    if not base.postgres_role_exists(username):
        raise RuntimeError("PostgreSQL application role is unavailable for restore")
    owner = _postgres_database_owner(database_name)
    if owner != base.POSTGRES_ADMIN_USER:
        raise RuntimeError("PostgreSQL restore target is not owned by the Ithute hosting admin")
    args = [
        PG_RESTORE,
        *base.postgres_connection_args(),
        "--dbname", database_name,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--role", username,
        str(backup),
    ]
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, **base.postgres_environment()}, timeout=3600, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"pg_restore failed: {detail}")


def _mysql_backup(database_name: str, temporary: pathlib.Path) -> None:
    if not base.MYSQL_ADMIN_HOST or not base.MYSQL_ADMIN_USER or not base.MYSQL_ADMIN_PASSWORD:
        raise RuntimeError("MySQL backup is not configured on this hosting node")
    args = [
        MYSQLDUMP,
        "--host", base.MYSQL_ADMIN_HOST,
        "--port", str(base.MYSQL_ADMIN_PORT),
        "--user", base.MYSQL_ADMIN_USER,
        "--single-transaction",
        "--quick",
        "--routines",
        "--triggers",
        "--events",
        "--hex-blob",
        "--set-gtid-purged=OFF",
        database_name,
    ]
    _run_to_file(args, temporary, env={"MYSQL_PWD": base.MYSQL_ADMIN_PASSWORD})


def _mysql_restore(database_name: str, backup: pathlib.Path) -> None:
    if not base.MYSQL_ADMIN_HOST or not base.MYSQL_ADMIN_USER or not base.MYSQL_ADMIN_PASSWORD:
        raise RuntimeError("MySQL restore is not configured on this hosting node")
    base.mysql_exec(f"DROP DATABASE IF EXISTS `{database_name}`; CREATE DATABASE `{database_name}`;")
    args = [
        base.MYSQL,
        "--host", base.MYSQL_ADMIN_HOST,
        "--port", str(base.MYSQL_ADMIN_PORT),
        "--user", base.MYSQL_ADMIN_USER,
        "--database", database_name,
    ]
    _run_from_file(args, backup, env={"MYSQL_PWD": base.MYSQL_ADMIN_PASSWORD})


def process_database_backup(work: dict[str, Any]) -> None:
    backup_id, operation, engine, database_name, username, final = _validate_work(work)
    storage_key = str(work.get("storage_key") or "")
    try:
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        final.parent.mkdir(parents=True, exist_ok=True)
        if operation == "backup":
            with tempfile.NamedTemporaryFile(prefix="db-backup-", dir=final.parent, delete=False) as handle:
                temporary = pathlib.Path(handle.name)
            try:
                if engine == "postgresql":
                    _postgres_backup(database_name, username, temporary)
                else:
                    _mysql_backup(database_name, temporary)
                size = temporary.stat().st_size
                if size <= 0 or size > MAX_BACKUP_BYTES:
                    raise RuntimeError("Database backup size is invalid or exceeds the node backup limit")
                digest = _sha256(temporary)
                os.replace(temporary, final)
                os.chmod(final, 0o600)
                # If remote replication is required, any upload/verification
                # failure keeps the control-plane backup in failed state.
                backup_remote.replicate(final, storage_key, digest, size)
                report_database_backup(backup_id, True, sha256=digest, size_bytes=size)
                base.log(f"database backup {backup_id} stored {final} and remote policy satisfied")
            finally:
                temporary.unlink(missing_ok=True)
            return

        expected_sha = str(work.get("sha256") or "").lower()
        expected_size = int(work.get("size_bytes") or 0)
        if len(expected_sha) != 64 or expected_size <= 0 or expected_size > MAX_BACKUP_BYTES:
            raise RuntimeError("Database restore metadata is invalid")
        _ensure_verified_backup_local(storage_key, final, expected_sha, expected_size)
        if engine == "postgresql":
            _postgres_restore(database_name, username, final)
        else:
            _mysql_restore(database_name, final)
        report_database_backup(backup_id, True)
        base.log(f"database restore {backup_id} complete from verified backup")
    except Exception as exc:
        error = str(exc)[:1900]
        base.log(f"database backup operation {backup_id} failed: {error}")
        try:
            report_database_backup(backup_id, False, message=error)
        except Exception as report_exc:
            base.log(f"could not report database backup failure: {report_exc}")


def handle_signal(signum: int, frame: Any) -> None:
    runtime.handle_signal(signum, frame)


def main() -> int:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    base.docker("version", "--format", "{{.Server.Version}}")
    backup_remote.require_configuration()
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    base.log(
        f"starting {AGENT_VERSION}; hosted network pool={HOSTED_NETWORK_POOL} /{HOSTED_NETWORK_PREFIX}; "
        f"off-node backups={'enabled' if backup_remote.enabled() else 'optional-disabled'}"
    )
    last_heartbeat = 0.0
    while not base.STOP:
        now = time.monotonic()
        try:
            if now - last_heartbeat >= base.HEARTBEAT_SECONDS:
                base.api(
                    "/hosting/agent/heartbeat",
                    {
                        "version": AGENT_VERSION,
                        "origin_bind_ip": base.ORIGIN_BIND_IP or None,
                        "capabilities": {
                            "postgres_physical_replication": postgres_physical_replication_capabilities(),
                        },
                    },
                )
                last_heartbeat = now

            group_failover = claim_postgres_group_failover()
            if group_failover:
                process_postgres_group_failover(group_failover)
                continue

            topology_repair = claim_postgres_topology_repair()
            if topology_repair:
                process_postgres_topology_repair(topology_repair)
                continue

            database_failover = claim_database_failover()
            if database_failover:
                process_database_failover(database_failover)
                continue

            database_work = base.claim_database()
            if database_work:
                base.process_database(database_work)
                continue

            project_work = runtime.claim_project_operation()
            if project_work:
                runtime.safe_process_project_operation(project_work)
                continue

            backup_work = claim_database_backup()
            if backup_work:
                process_database_backup(backup_work)
                continue

            deployment_work = base.claim()
            if deployment_work:
                base.activate(deployment_work)
                continue
        except Exception as exc:
            base.log(f"poll failed: {exc}")

        for _ in range(base.POLL_SECONDS):
            if base.STOP:
                break
            time.sleep(1)

    base.log("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
