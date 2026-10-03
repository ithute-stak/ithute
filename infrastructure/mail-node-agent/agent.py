#!/usr/bin/env python3
"""Ithute Mail Node Agent.

Runs on an external VPS/dedicated mail node. It receives only mailbox-state
commands assigned to that node and keeps Docker Mailserver's account file in
sync without exposing SSH credentials to the Ithute control plane.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import signal
import socket
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AGENT_VERSION = "ithute-mail-agent/1"
STOP = False


def required_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


API_URL = required_env("ITHUTE_API_URL").rstrip("/")
AGENT_TOKEN = required_env("ITHUTE_MAIL_AGENT_TOKEN")
ACCOUNTS_FILE = Path(required_env("ITHUTE_MAIL_ACCOUNTS_FILE", "/tmp/docker-mailserver/postfix-accounts.cf"))
QUOTAS_FILE = Path(required_env("ITHUTE_MAIL_QUOTAS_FILE", "/tmp/docker-mailserver/dovecot-quotas.cf"))
STORAGE_PATH = Path(required_env("ITHUTE_MAIL_STORAGE_PATH", "/srv/ithute-mail"))
MAIL_HOSTNAME = required_env("ITHUTE_MAIL_HOSTNAME")
POLL_SECONDS = max(5, int(os.getenv("ITHUTE_MAIL_POLL_SECONDS", "10")))
HEARTBEAT_SECONDS = max(15, int(os.getenv("ITHUTE_MAIL_HEARTBEAT_SECONDS", "60")))
ALLOW_HTTP = os.getenv("ITHUTE_MAIL_ALLOW_HTTP", "false").lower() == "true"
BACKUP_ROOT = Path(os.getenv("ITHUTE_MAIL_BACKUP_ROOT", "/var/lib/ithute-mail-node/backups")).resolve()
BACKUP_REMOTE = os.getenv("ITHUTE_MAIL_BACKUP_REMOTE", "").strip().rstrip("/")
BACKUP_REMOTE_REQUIRED = os.getenv("ITHUTE_MAIL_BACKUP_REMOTE_REQUIRED", "true").lower() == "true"
RCLONE = os.getenv("ITHUTE_MAIL_RCLONE", "rclone").strip()
RCLONE_CONFIG = os.getenv("ITHUTE_MAIL_RCLONE_CONFIG", "/etc/ithute-mail-node/rclone.conf").strip()
MAIL_CONTAINER = os.getenv("ITHUTE_MAIL_CONTAINER", "ithute-mail").strip()

if not API_URL.startswith("https://") and not ALLOW_HTTP:
    raise RuntimeError("ITHUTE_API_URL must use HTTPS unless ITHUTE_MAIL_ALLOW_HTTP=true")
if not AGENT_TOKEN.startswith("ith_mail_"):
    raise RuntimeError("ITHUTE_MAIL_AGENT_TOKEN is not a mail-node credential")
if not ACCOUNTS_FILE.is_absolute() or not QUOTAS_FILE.is_absolute() or not STORAGE_PATH.is_absolute():
    raise RuntimeError("Mail account, quota and storage paths must be absolute")
if ACCOUNTS_FILE.parent != QUOTAS_FILE.parent:
    raise RuntimeError("ITHUTE_MAIL_ACCOUNTS_FILE and ITHUTE_MAIL_QUOTAS_FILE must share the DMS config directory")
if not BACKUP_ROOT.is_absolute():
    raise RuntimeError("ITHUTE_MAIL_BACKUP_ROOT must be absolute")
if BACKUP_REMOTE_REQUIRED and not BACKUP_REMOTE:
    raise RuntimeError("ITHUTE_MAIL_BACKUP_REMOTE is required when ITHUTE_MAIL_BACKUP_REMOTE_REQUIRED=true")


def log(message: str) -> None:
    print(f"[mail-node-agent] {message}", flush=True)


def api(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_URL}/api/v1{path}",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Ithute-Mail-Agent": AGENT_TOKEN,
            "User-Agent": AGENT_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Control-plane HTTP {exc.code}: {detail}") from exc


def _validate_account(address: str, password_hash: str) -> tuple[str, str]:
    clean_address = address.strip().lower()
    clean_hash = password_hash.strip()
    if not clean_address or clean_address.count("@") != 1 or any(char in clean_address for char in "|\r\n"):
        raise RuntimeError("Mailbox address is invalid")
    if not clean_hash.startswith("{SHA512-CRYPT}$6$") or any(char in clean_hash for char in "|\r\n"):
        raise RuntimeError("Mailbox password hash is invalid")
    return clean_address, clean_hash


def _write_in_place(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(path, 0o600)


def write_account(address: str, password_hash: str, quota_bytes: int, active: bool) -> None:
    clean_address, clean_hash = _validate_account(address, password_hash)
    if quota_bytes <= 0:
        raise RuntimeError("Mailbox quota must be greater than zero")

    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ACCOUNTS_FILE.parent / ".ithute-mail-agent.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

        existing_accounts = ACCOUNTS_FILE.read_text(encoding="utf-8").splitlines() if ACCOUNTS_FILE.exists() else []
        account_lines = []
        for line in existing_accounts:
            candidate = line.split("|", 1)[0].strip().lower() if "|" in line else ""
            if candidate != clean_address:
                account_lines.append(line)
        if active:
            account_lines.append(f"{clean_address}|{clean_hash}")
        account_payload = "\n".join(account_lines)
        if account_payload:
            account_payload += "\n"

        existing_quotas = QUOTAS_FILE.read_text(encoding="utf-8").splitlines() if QUOTAS_FILE.exists() else []
        quota_lines = []
        for line in existing_quotas:
            candidate = line.split(":", 1)[0].strip().lower() if ":" in line else ""
            if candidate != clean_address:
                quota_lines.append(line)
        if active:
            quota_lines.append(f"{clean_address}:{quota_bytes}")
        quota_payload = "\n".join(quota_lines)
        if quota_payload:
            quota_payload += "\n"

        _write_in_place(ACCOUNTS_FILE, account_payload)
        _write_in_place(QUOTAS_FILE, quota_payload)
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _tcp_ready(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3):
            return True
    except OSError:
        return False


def _imap_tls_ready() -> tuple[bool, str | None, str | None]:
    context = ssl.create_default_context()
    try:
        with socket.create_connection((MAIL_HOSTNAME, 993), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname=MAIL_HOSTNAME) as tls:
                certificate = tls.getpeercert()
                raw_not_after = certificate.get("notAfter")
                not_after = None
                if raw_not_after:
                    not_after = datetime.fromtimestamp(ssl.cert_time_to_seconds(raw_not_after), tz=timezone.utc).isoformat()
                return True, not_after, None
    except Exception as exc:
        return False, None, str(exc)[:500]


def heartbeat() -> None:
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(STORAGE_PATH)
    smtp_ready = _tcp_ready(25) and _tcp_ready(587)
    imap_ready = _tcp_ready(993)
    tls_ready, tls_not_after, tls_error = _imap_tls_ready() if imap_ready else (False, None, "IMAPS port 993 is not reachable")
    readiness_error = None
    if not smtp_ready:
        readiness_error = "SMTP ports 25/587 are not both reachable"
    if not imap_ready:
        readiness_error = "IMAPS port 993 is not reachable"
    if imap_ready and not tls_ready:
        readiness_error = f"IMAPS TLS validation failed: {tls_error}"

    api("/mail-node-agent/heartbeat", {
        "version": AGENT_VERSION,
        "total_storage_bytes": usage.total,
        "used_storage_bytes": usage.used,
        "capabilities": ["mail", "storage"],
        "smtp_ready": smtp_ready,
        "imap_ready": imap_ready,
        "tls_ready": tls_ready,
        "tls_not_after": tls_not_after,
        "readiness_error": readiness_error,
    })


def process(command: dict[str, Any]) -> None:
    command_id = str(command["id"])
    payload = command.get("payload")
    if command.get("operation") != "sync" or not isinstance(payload, dict):
        raise RuntimeError("Unsupported mail-node command")
    address = str(payload.get("address") or "")
    password_hash = str(payload.get("password_hash") or "")
    quota_bytes = int(payload.get("quota_bytes") or 0)
    status = str(payload.get("status") or "")
    write_account(address, password_hash, quota_bytes, active=status == "active")
    api(f"/mail-node-agent/commands/{command_id}/status", {"status": "completed"})


def claim_once() -> bool:
    result = api("/mail-node-agent/commands/claim", {})
    command = result.get("command")
    if not isinstance(command, dict):
        return False
    try:
        process(command)
        log(f"completed command {command.get('id')}")
    except Exception as exc:
        message = str(exc)[:3900]
        log(f"command {command.get('id')} failed: {message}")
        try:
            api(f"/mail-node-agent/commands/{command.get('id')}/status", {"status": "failed", "message": message})
        except Exception as report_exc:
            log(f"could not report failure: {report_exc}")
    return True


def _run(args: list[str], *, timeout: int = 3600) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"{Path(args[0]).name} failed: {detail}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remote_uri(snapshot_key: str) -> str:
    if not BACKUP_REMOTE:
        return ""
    return f"{BACKUP_REMOTE}/{snapshot_key}.tar.gz"


def _rclone_args(*args: str) -> list[str]:
    command = [RCLONE]
    if RCLONE_CONFIG:
        command.extend(["--config", RCLONE_CONFIG])
    command.extend(args)
    return command


def create_snapshot(snapshot_key: str) -> dict[str, Any]:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    archive = BACKUP_ROOT / f"{snapshot_key}.tar.gz"
    if archive.exists():
        archive.unlink()

    with tarfile.open(archive, "w:gz") as tar:
        if STORAGE_PATH.exists():
            for child in sorted(STORAGE_PATH.iterdir()):
                tar.add(child, arcname=child.name, recursive=True)

    size = archive.stat().st_size
    checksum = _sha256(archive)
    remote_uri = _remote_uri(snapshot_key)
    if remote_uri:
        _run(_rclone_args("copyto", str(archive), remote_uri))
    elif BACKUP_REMOTE_REQUIRED:
        raise RuntimeError("Off-node backup remote is not configured")

    return {
        "snapshot_key": snapshot_key,
        "remote_uri": remote_uri or None,
        "size_bytes": size,
        "checksum_sha256": checksum,
    }


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            candidate = (root / member.name).resolve()
            if candidate != root and root not in candidate.parents:
                raise RuntimeError("Snapshot contains an unsafe path")
            if member.issym() or member.islnk():
                raise RuntimeError("Snapshot contains unsupported links")
        tar.extractall(destination, filter="data")


def restore_snapshot(remote_uri: str, snapshot_key: str, checksum: str | None) -> dict[str, Any]:
    if not remote_uri:
        raise RuntimeError("Failover snapshot does not have an off-node remote URI")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    archive = BACKUP_ROOT / f"{snapshot_key}.restore.tar.gz"
    _run(_rclone_args("copyto", remote_uri, str(archive)))
    actual_checksum = _sha256(archive)
    if checksum and actual_checksum.lower() != checksum.lower():
        raise RuntimeError("Snapshot checksum verification failed")

    parent = STORAGE_PATH.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ithute-mail-restore-", dir=parent) as tmp:
        staging = Path(tmp) / "mail-data"
        _safe_extract(archive, staging)

        _run(["docker", "stop", "--time", "30", MAIL_CONTAINER], timeout=90)
        previous = parent / f".{STORAGE_PATH.name}.pre-restore-{int(time.time())}"
        try:
            if STORAGE_PATH.exists():
                STORAGE_PATH.rename(previous)
            staging.rename(STORAGE_PATH)
            _run(["docker", "start", MAIL_CONTAINER], timeout=90)
            if previous.exists():
                shutil.rmtree(previous)
        except Exception:
            if STORAGE_PATH.exists():
                shutil.rmtree(STORAGE_PATH)
            if previous.exists():
                previous.rename(STORAGE_PATH)
            _run(["docker", "start", MAIL_CONTAINER], timeout=90)
            raise

    return {
        "snapshot_key": snapshot_key,
        "checksum_sha256": actual_checksum,
        "restored": True,
    }


def process_operation(operation: dict[str, Any]) -> None:
    operation_id = str(operation["id"])
    kind = str(operation.get("operation") or "")
    payload = operation.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError("Mail node operation payload is invalid")

    if kind == "backup":
        result = create_snapshot(str(payload.get("snapshot_key") or ""))
    elif kind == "restore_failover":
        result = restore_snapshot(
            str(payload.get("remote_uri") or ""),
            str(payload.get("snapshot_key") or ""),
            str(payload.get("checksum_sha256") or "") or None,
        )
    else:
        raise RuntimeError(f"Unsupported mail node operation: {kind}")

    api(f"/mail-node-agent/operations/{operation_id}/status", {"status": "completed", "result": result})


def claim_operation_once() -> bool:
    result = api("/mail-node-agent/operations/claim", {})
    operation = result.get("operation")
    if not isinstance(operation, dict):
        return False
    try:
        process_operation(operation)
        log(f"completed node operation {operation.get('id')}")
    except Exception as exc:
        message = str(exc)[:3900]
        log(f"node operation {operation.get('id')} failed: {message}")
        try:
            api(
                f"/mail-node-agent/operations/{operation.get('id')}/status",
                {"status": "failed", "message": message, "result": {}},
            )
        except Exception as report_exc:
            log(f"could not report node operation failure: {report_exc}")
    return True


def stop(_signum, _frame) -> None:
    global STOP
    STOP = True


def main() -> None:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last_heartbeat = 0.0
    log("starting")
    while not STOP:
        now = time.monotonic()
        try:
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                heartbeat()
                last_heartbeat = now
            worked = claim_operation_once()
            if not worked:
                worked = claim_once()
        except Exception as exc:
            log(f"control-plane error: {exc}")
            worked = False
        if not worked:
            time.sleep(POLL_SECONDS)
    log("stopped")


if __name__ == "__main__":
    main()
