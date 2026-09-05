#!/usr/bin/env python3
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAIL_OPS_URL = os.getenv("MAIL_OPS_URL", "http://postfix:9080").rstrip("/")
MAIL_OPS_TOKEN = os.getenv("MAIL_OPS_TOKEN", "")
STATUS_FILE = Path(os.getenv("BACKUP_STATUS_FILE", "/workspace/status/last-run.json"))
PORT = int(os.getenv("OPS_EXPORTER_PORT", "9108"))


def _mail_json(path: str) -> dict:
    request = urllib.request.Request(
        f"{MAIL_OPS_URL}{path}",
        headers={"X-Mail-Ops-Token": MAIL_OPS_TOKEN},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read() or b"{}")


def _metrics() -> str:
    lines = [
        "# HELP mailbox_dns_mail_queue_total Current Postfix queue item count.",
        "# TYPE mailbox_dns_mail_queue_total gauge",
        "# HELP mailbox_dns_mail_queue_deferred Current Postfix deferred queue item count.",
        "# TYPE mailbox_dns_mail_queue_deferred gauge",
        "# HELP mailbox_dns_mail_ops_ready Whether the private Postfix operations endpoint is reachable.",
        "# TYPE mailbox_dns_mail_ops_ready gauge",
        "# HELP mailbox_dns_backup_last_run_success Whether the most recent scheduled backup completed successfully.",
        "# TYPE mailbox_dns_backup_last_run_success gauge",
        "# HELP mailbox_dns_backup_last_run_age_seconds Age of the most recent scheduled backup completion record.",
        "# TYPE mailbox_dns_backup_last_run_age_seconds gauge",
    ]

    try:
        queue = _mail_json("/queue")
        deferred = _mail_json("/queue/deferred")
        queue_count = len(queue.get("items", []))
        deferred_count = deferred.get("total", len(deferred.get("items", [])))
        lines += [
            "mailbox_dns_mail_ops_ready 1",
            f"mailbox_dns_mail_queue_total {int(queue_count)}",
            f"mailbox_dns_mail_queue_deferred {int(deferred_count)}",
        ]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        lines += [
            "mailbox_dns_mail_ops_ready 0",
            "mailbox_dns_mail_queue_total 0",
            "mailbox_dns_mail_queue_deferred 0",
        ]

    success = 0
    age = -1
    try:
        payload = json.loads(STATUS_FILE.read_text())
        success = 1 if payload.get("status") == "success" else 0
        finished = payload.get("finished_at")
        if finished:
            timestamp = time.strptime(finished, "%Y-%m-%dT%H:%M:%SZ")
            age = max(0, int(time.time() - time.mktime(timestamp)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    lines += [
        f"mailbox_dns_backup_last_run_success {success}",
        f"mailbox_dns_backup_last_run_age_seconds {age}",
    ]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        elif self.path == "/metrics":
            body = _metrics().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
        else:
            body = b"not found\n"
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
