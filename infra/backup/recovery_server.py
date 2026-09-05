#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = os.environ.get("RECOVERY_OPS_TOKEN", "")
ADDRESS_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$")


def recover(address: str, snapshot_id: str | None) -> dict:
    if not ADDRESS_RE.fullmatch(address) or ".." in address:
        raise ValueError("Invalid mailbox address")
    local, domain = address.lower().split("@", 1)
    source_path = f"/data/mail/{domain}/{local}"
    snapshot = snapshot_id or "latest"
    with tempfile.TemporaryDirectory(prefix="mailbox-recover-", dir="/restore") as target:
        cmd = ["restic", "restore", snapshot, "--target", target, "--include", source_path]
        completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
        if completed.returncode != 0:
            raise RuntimeError(completed.stdout[-4000:])
        restored = Path(target) / "data" / "mail" / domain / local
        if not restored.exists():
            raise RuntimeError("Selected snapshot does not contain the mailbox")
        destination = Path("/data/mail") / domain / local
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(restored, destination, dirs_exist_ok=True, copy_function=shutil.copy2)
        for restored_path in [destination, *destination.rglob("*")]:
            os.chown(restored_path, 5000, 5000)
        count = sum(1 for p in restored.rglob("*") if p.is_file())
        return {"restored_files": count, "snapshot_id": snapshot, "mailbox_address": address}


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/recover":
            self._json(404, {"error": "not found"})
            return
        supplied = self.headers.get("Authorization", "")
        if not TOKEN or supplied != f"Bearer {TOKEN}":
            self._json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            result = recover(str(payload.get("mailbox_address", "")), payload.get("snapshot_id"))
            self._json(200, result)
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self._json(422, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("recovery", self.address_string(), fmt % args, flush=True)


if __name__ == "__main__":
    if len(TOKEN) < 24:
        raise SystemExit("RECOVERY_OPS_TOKEN must be at least 24 characters")
    ThreadingHTTPServer(("0.0.0.0", 9081), Handler).serve_forever()
