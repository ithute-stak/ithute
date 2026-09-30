#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import UUID

from zip_safety import UnsafeZip, inspect_zip, safe_object_path

API_URL = os.environ["ITHUTE_API_URL"].rstrip("/")
SERVICE_TOKEN = os.environ["ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN"].strip()
LISTEN_HOST = os.getenv("ITHUTE_HOSTING_UPLOAD_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.getenv("ITHUTE_HOSTING_UPLOAD_LISTEN_PORT", "8096"))
QUARANTINE_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_UPLOAD_QUARANTINE_ROOT", "/var/lib/ithute-upload/quarantine"))
VERIFIED_ROOT = pathlib.Path(os.getenv("ITHUTE_HOSTING_UPLOAD_VERIFIED_ROOT", "/var/lib/ithute-upload/verified"))
MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024

if not API_URL.startswith("https://") and os.getenv("ITHUTE_HOSTING_ALLOW_HTTP", "false").lower() != "true":
    raise RuntimeError("ITHUTE_API_URL must use HTTPS")
if not SERVICE_TOKEN.startswith("ith_upload_"):
    raise RuntimeError("ITHUTE_HOSTING_UPLOAD_SERVICE_TOKEN is invalid")


def api(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{API_URL}/api/v1{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Ithute-Upload-Service": SERVICE_TOKEN,
            "User-Agent": "ithute-hosting-upload/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"control-plane HTTP {exc.code}: {detail}") from exc


def fail(source_id: str, message: str) -> None:
    try:
        api(f"/hosting/upload/sources/{source_id}/failed", {"message": message[:1900]})
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "IthuteHostingUpload/1"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._json(200, {"ok": True, "service": "hosting-upload"})
            return
        self._json(404, {"detail": "Not found"})

    def do_PUT(self) -> None:
        prefix = "/v1/uploads/"
        if not self.path.startswith(prefix):
            self._json(404, {"detail": "Not found"})
            return
        source_id = self.path[len(prefix):].split("?", 1)[0].strip()
        try:
            UUID(source_id)
        except ValueError:
            self._json(404, {"detail": "Invalid source id"})
            return

        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ith_zip_"):
            self._json(401, {"detail": "One-time ZIP upload credential required"})
            return
        upload_token = auth[7:].strip()
        if self.headers.get_content_type() not in {"application/zip", "application/octet-stream"}:
            self._json(415, {"detail": "Upload must be application/zip"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_ZIP_BYTES:
            self._json(413, {"detail": "ZIP upload size is invalid or exceeds 2 GiB"})
            return

        try:
            manifest = api(f"/hosting/upload/sources/{source_id}/authorize", {"upload_token": upload_token})
            expected_size = int(manifest["expected_size_bytes"])
            if length != expected_size:
                raise RuntimeError("Content-Length does not match registered ZIP size")
            object_key = str(manifest["object_key"])
            max_files = int(manifest["max_files"])
            max_unpacked = int(manifest["max_unpacked_size_bytes"])
        except Exception as exc:
            self._json(409, {"detail": str(exc)})
            return

        QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
        VERIFIED_ROOT.mkdir(parents=True, exist_ok=True)
        temporary: pathlib.Path | None = None
        final: pathlib.Path | None = None
        try:
            hasher = hashlib.sha256()
            remaining = length
            with tempfile.NamedTemporaryFile(prefix="upload-", suffix=".zip", dir=QUARANTINE_ROOT, delete=False) as handle:
                temporary = pathlib.Path(handle.name)
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError("Upload ended before Content-Length bytes were received")
                    handle.write(chunk)
                    hasher.update(chunk)
                    remaining -= len(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            digest = hasher.hexdigest()
            expected_sha = manifest.get("expected_sha256")
            if expected_sha and digest != expected_sha:
                raise UnsafeZip("ZIP checksum does not match registered metadata")
            inspection = inspect_zip(temporary, max_files=max_files, max_unpacked_bytes=max_unpacked)
            final = safe_object_path(VERIFIED_ROOT, object_key)
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, final)
            temporary = None
            os.chmod(final, 0o440)
            api(
                f"/hosting/upload/sources/{source_id}/complete",
                {
                    "sha256": digest,
                    "size_bytes": length,
                    "unpacked_size_bytes": inspection.unpacked_size_bytes,
                    "file_count": inspection.file_count,
                },
            )
            self._json(201, {"verified": True, "source_id": source_id, "sha256": digest})
        except Exception as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if final is not None:
                final.unlink(missing_ok=True)
            fail(source_id, str(exc))
            self._json(422, {"verified": False, "detail": str(exc)[:1900]})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[hosting-upload] {self.address_string()} {format % args}", flush=True)


def main() -> int:
    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
    VERIFIED_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    print(f"[hosting-upload] listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
