from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

RCLONE = os.getenv("ITHUTE_HOSTING_RCLONE", "rclone")
REMOTE = os.getenv("ITHUTE_HOSTING_BACKUP_REMOTE", "").strip().rstrip("/")
REMOTE_REQUIRED = os.getenv("ITHUTE_HOSTING_BACKUP_REMOTE_REQUIRED", "false").lower() == "true"
RCLONE_CONFIG = os.getenv("ITHUTE_HOSTING_RCLONE_CONFIG", "").strip()


def enabled() -> bool:
    return bool(REMOTE)


def require_configuration() -> None:
    if REMOTE_REQUIRED and not REMOTE:
        raise RuntimeError("Off-node database backup remote is required but not configured")


def remote_object(storage_key: str) -> str:
    if not REMOTE:
        raise RuntimeError("Off-node database backup remote is not configured")
    if not storage_key or storage_key.startswith("/") or "\\" in storage_key or ".." in pathlib.PurePosixPath(storage_key).parts:
        raise RuntimeError("Backup storage key is unsafe for remote replication")
    return f"{REMOTE}/{storage_key}"


def _env() -> dict[str, str]:
    env = dict(os.environ)
    if RCLONE_CONFIG:
        env["RCLONE_CONFIG"] = RCLONE_CONFIG
    return env


def _run(args: list[str], *, timeout: int = 7200) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, env=_env(), timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout)[-2000:]
        raise RuntimeError(f"off-node backup command failed: {detail}")
    return result


def _remote_size(target: str) -> int:
    result = _run([RCLONE, "lsl", target], timeout=120)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("Off-node backup object could not be uniquely verified")
    try:
        return int(lines[0].split(maxsplit=1)[0])
    except (ValueError, IndexError) as exc:
        raise RuntimeError("Off-node backup size response is invalid") from exc


def replicate(local_path: pathlib.Path, storage_key: str, sha256: str, size_bytes: int) -> None:
    require_configuration()
    if not REMOTE:
        return
    if not local_path.is_file() or local_path.is_symlink():
        raise RuntimeError("Local database backup is unavailable for off-node replication")
    if local_path.stat().st_size != size_bytes:
        raise RuntimeError("Local database backup size changed before off-node replication")

    target = remote_object(storage_key)
    _run([RCLONE, "copyto", str(local_path), target, "--immutable"])
    if _remote_size(target) != size_bytes:
        raise RuntimeError("Off-node database backup size does not match local backup")

    # Store the control-plane SHA-256 beside the object. Restore still hashes the
    # downloaded payload itself against the database record before use.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        sidecar = pathlib.Path(handle.name)
        handle.write(f"{sha256}  {pathlib.PurePosixPath(storage_key).name}\n")
    try:
        _run([RCLONE, "copyto", str(sidecar), f"{target}.sha256", "--immutable"])
    finally:
        sidecar.unlink(missing_ok=True)


def hydrate(storage_key: str, destination: pathlib.Path) -> bool:
    """Restore a missing local backup from remote storage.

    Returns False only when no remote is configured. Integrity is intentionally
    verified by the caller against the control-plane SHA-256 and size after the
    download completes.
    """
    require_configuration()
    if not REMOTE:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.remote-download")
    temporary.unlink(missing_ok=True)
    try:
        _run([RCLONE, "copyto", remote_object(storage_key), str(temporary)])
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
        return True
    finally:
        temporary.unlink(missing_ok=True)
