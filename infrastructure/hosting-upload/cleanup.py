#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request
from typing import Any

from zip_safety import safe_object_path

API_URL = os.environ["ITHUTE_API_URL"].rstrip("/")
SERVICE_TOKEN = os.environ["ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN"].strip()
QUARANTINE_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_UPLOAD_QUARANTINE_ROOT", "/var/lib/ithute-upload/quarantine"))
VERIFIED_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_UPLOAD_VERIFIED_ROOT", "/var/lib/ithute-upload/verified"))
INTERVAL_SECONDS = max(300, int(os.getenv("ITHUTE_HOSTING_CLEANUP_INTERVAL_SECONDS", "3600")))
QUARANTINE_GRACE_SECONDS = max(3600, int(os.getenv("ITHUTE_HOSTING_QUARANTINE_RETENTION_HOURS", "24")) * 3600)
ORPHAN_VERIFIED_GRACE_SECONDS = max(86400, int(os.getenv("ITHUTE_HOSTING_ORPHAN_VERIFIED_RETENTION_HOURS", "168")) * 3600)

if not API_URL.startswith("https://") and os.getenv("ITHUTE_HOSTING_ALLOW_HTTP", "false").lower() != "true":
    raise RuntimeError("ITHUTE_API_URL must use HTTPS")
if not SERVICE_TOKEN.startswith("ith_upload_"):
    raise RuntimeError("ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN is invalid")


def log(message: str) -> None:
    print(f"[hosting-upload-cleanup] {message}", flush=True)


def api(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{API_URL}/api/v1{path}",
        data=json.dumps(payload or {}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Ithute-Upload-Service": SERVICE_TOKEN,
            "User-Agent": "ithute-hosting-upload-cleanup/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"control-plane HTTP {exc.code}: {detail}") from exc


def old_enough(path: pathlib.Path, grace_seconds: int, now: float) -> bool:
    try:
        return now - path.stat().st_mtime >= grace_seconds
    except FileNotFoundError:
        return False


def remove_empty_parents(path: pathlib.Path, root: pathlib.Path) -> None:
    current = path.parent
    resolved_root = root.resolve()
    while current != resolved_root and resolved_root in current.resolve().parents:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def clean_quarantine(now: float) -> tuple[int, int]:
    removed = 0
    reclaimed = 0
    if not QUARANTINE_ROOT.exists():
        return removed, reclaimed
    root = QUARANTINE_ROOT.resolve()
    for path in list(root.rglob("*")):
        if not path.is_file() or not old_enough(path, QUARANTINE_GRACE_SECONDS, now):
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            removed += 1
            reclaimed += size
            remove_empty_parents(path, root)
        except FileNotFoundError:
            continue
    return removed, reclaimed


def clean_verified(now: float, referenced_keys: set[str]) -> tuple[int, int]:
    removed = 0
    reclaimed = 0
    if not VERIFIED_ROOT.exists():
        return removed, reclaimed
    root = VERIFIED_ROOT.resolve()

    referenced_paths: set[pathlib.Path] = set()
    for key in referenced_keys:
        try:
            referenced_paths.add(safe_object_path(root, key).resolve())
        except Exception as exc:
            # A malformed database key makes cleanup unsafe. Refuse the cycle.
            raise RuntimeError(f"control plane returned an invalid verified object key: {exc}") from exc

    for path in list(root.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in referenced_paths or not old_enough(path, ORPHAN_VERIFIED_GRACE_SECONDS, now):
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            removed += 1
            reclaimed += size
            remove_empty_parents(path, root)
        except FileNotFoundError:
            continue
    return removed, reclaimed


def run_once() -> None:
    inventory = api("/hosting/upload/storage/inventory")
    raw_keys = inventory.get("referenced_object_keys")
    if not isinstance(raw_keys, list) or any(not isinstance(item, str) for item in raw_keys):
        raise RuntimeError("control plane returned an invalid ZIP storage inventory")
    referenced = set(raw_keys)
    now = time.time()
    q_count, q_bytes = clean_quarantine(now)
    v_count, v_bytes = clean_verified(now, referenced)
    log(
        f"cycle complete: quarantine_removed={q_count} quarantine_bytes={q_bytes} "
        f"verified_orphans_removed={v_count} verified_orphan_bytes={v_bytes} referenced={len(referenced)}"
    )


def main() -> int:
    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
    VERIFIED_ROOT.mkdir(parents=True, exist_ok=True)
    log("starting safe retention worker")
    while True:
        try:
            run_once()
        except Exception as exc:
            # Fail closed for the cycle. Never delete verified objects without a
            # complete, valid control-plane inventory.
            log(f"cleanup cycle skipped: {exc}")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
