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
import signal
import subprocess
import tempfile
import time
from typing import Any

import agent_v3 as runtime
from network_policy import choose_project_subnet, parse_existing_subnets, parse_pool

base = runtime.base
AGENT_VERSION = "ithute-hosting-agent/4"
base.AGENT_VERSION = AGENT_VERSION
BACKUP_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_DATABASE_BACKUP_ROOT", "/var/lib/ithute-hosting/database-backups"))
PG_DUMP = os.getenv("ITHUTE_HOSTING_PG_DUMP", "pg_dump")
PG_RESTORE = os.getenv("ITHUTE_HOSTING_PG_RESTORE", "pg_restore")
MYSQLDUMP = os.getenv("ITHUTE_HOSTING_MYSQLDUMP", "mysqldump")
MAX_BACKUP_BYTES = int(os.getenv("ITHUTE_HOSTING_DATABASE_BACKUP_MAX_BYTES", str(20 * 1024 * 1024 * 1024)))
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


def _validate_work(work: dict[str, Any]) -> tuple[str, str, str, str, pathlib.Path]:
    backup_id = str(work.get("id") or "")
    operation = str(work.get("operation") or "")
    database = work.get("database")
    if not backup_id or operation not in {"backup", "restore"} or not isinstance(database, dict):
        raise RuntimeError("Database backup job is incomplete")
    engine = str(database.get("engine") or "")
    database_name = str(database.get("database_name") or "")
    if engine not in {"postgresql", "mysql"}:
        raise RuntimeError("Database backup job has an unsupported engine")
    if not base.DB_IDENT_RE.fullmatch(database_name):
        raise RuntimeError("Database backup job contains an invalid database identifier")
    if operation == "restore" and str(database.get("status") or "") != "suspended":
        raise RuntimeError("Database must remain suspended during restore")
    return backup_id, operation, engine, database_name, _safe_storage_path(str(work.get("storage_key") or ""))


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


def _postgres_backup(database_name: str, temporary: pathlib.Path) -> None:
    args = [
        PG_DUMP,
        *base.postgres_connection_args(),
        "--dbname", database_name,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--file", str(temporary),
    ]
    result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env={**os.environ, **base.postgres_environment()}, timeout=3600, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.decode('utf-8', errors='replace')[-2000:]}")


def _postgres_restore(database_name: str, backup: pathlib.Path) -> None:
    owner = base.psql(f"SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname={base.sql_literal(database_name)}").strip()
    if not base.DB_USER_RE.fullmatch(owner):
        raise RuntimeError("Could not resolve the PostgreSQL application owner for restore")
    args = [
        PG_RESTORE,
        *base.postgres_connection_args(),
        "--dbname", database_name,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--role", owner,
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
    # The database is intentionally retained so the project user's existing
    # grants remain in place while the dump replaces schema/data contents.
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
    backup_id, operation, engine, database_name, final = _validate_work(work)
    try:
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        final.parent.mkdir(parents=True, exist_ok=True)
        if operation == "backup":
            with tempfile.NamedTemporaryFile(prefix="db-backup-", dir=final.parent, delete=False) as handle:
                temporary = pathlib.Path(handle.name)
            try:
                if engine == "postgresql":
                    _postgres_backup(database_name, temporary)
                else:
                    _mysql_backup(database_name, temporary)
                size = temporary.stat().st_size
                if size <= 0 or size > MAX_BACKUP_BYTES:
                    raise RuntimeError("Database backup size is invalid or exceeds the node backup limit")
                digest = _sha256(temporary)
                os.replace(temporary, final)
                os.chmod(final, 0o600)
                report_database_backup(backup_id, True, sha256=digest, size_bytes=size)
                base.log(f"database backup {backup_id} stored {final}")
            finally:
                temporary.unlink(missing_ok=True)
            return

        expected_sha = str(work.get("sha256") or "").lower()
        expected_size = int(work.get("size_bytes") or 0)
        if not final.is_file() or final.is_symlink():
            raise RuntimeError("Database backup file is unavailable")
        actual_size = final.stat().st_size
        if actual_size != expected_size or actual_size <= 0 or actual_size > MAX_BACKUP_BYTES:
            raise RuntimeError("Database backup size changed before restore")
        if _sha256(final) != expected_sha:
            raise RuntimeError("Database backup checksum changed before restore")
        if engine == "postgresql":
            _postgres_restore(database_name, final)
        else:
            _mysql_restore(database_name, final)
        report_database_backup(backup_id, True)
        base.log(f"database restore {backup_id} complete")
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
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    base.log(f"starting {AGENT_VERSION}; hosted network pool={HOSTED_NETWORK_POOL} /{HOSTED_NETWORK_PREFIX}")
    last_heartbeat = 0.0
    while not base.STOP:
        now = time.monotonic()
        try:
            if now - last_heartbeat >= base.HEARTBEAT_SECONDS:
                base.heartbeat()
                last_heartbeat = now

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
