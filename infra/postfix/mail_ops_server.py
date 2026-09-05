#!/usr/bin/env python3
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

TOKEN = os.environ.get("MAIL_OPS_TOKEN", "")
PORT = int(os.environ.get("MAIL_OPS_PORT", "9080"))
MAIL_HOSTNAME = os.environ.get("MAIL_HOSTNAME", "")
CERT_PATH = os.environ.get("MAIL_TLS_CERT_PATH", "/etc/postfix/tls/cert.pem")
QUEUE_ID_RE = re.compile(r"^[A-F0-9]{5,32}[*!]?$", re.IGNORECASE)


def run_command(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return proc.returncode, proc.stdout, proc.stderr


def queue_rows() -> list[dict]:
    code, out, err = run_command(["postqueue", "-j"])
    if code != 0:
        raise RuntimeError(err.strip() or "postqueue failed")
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def deferred_rows() -> list[dict]:
    return [row for row in queue_rows() if row.get("delay_reason")]


def tls_status() -> dict:
    if not os.path.isfile(CERT_PATH):
        return {"ready": False, "certificate_present": False, "hostname_matches": False, "days_remaining": None, "detail": "certificate file missing"}
    code, out, err = run_command(["openssl", "x509", "-in", CERT_PATH, "-noout", "-subject", "-issuer", "-enddate", "-ext", "subjectAltName"])
    if code != 0:
        return {"ready": False, "certificate_present": True, "hostname_matches": False, "days_remaining": None, "detail": err.strip() or "certificate inspection failed"}
    fields = {"raw": out}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("subject="):
            fields["subject"] = line.split("=", 1)[1].strip()
        elif line.startswith("issuer="):
            fields["issuer"] = line.split("=", 1)[1].strip()
        elif line.startswith("notAfter="):
            fields["not_after"] = line.split("=", 1)[1].strip()
    hostname = MAIL_HOSTNAME.rstrip(".").lower()
    normalized = out.lower()
    hostname_matches = bool(hostname) and (f"dns:{hostname}" in normalized or f"cn = {hostname}" in normalized or f"cn={hostname}" in normalized)
    days_remaining = None
    if fields.get("not_after"):
        try:
            expires = datetime.strptime(fields["not_after"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            days_remaining = int((expires - datetime.now(timezone.utc)).total_seconds() // 86400)
        except ValueError:
            pass
    self_signed = fields.get("subject") == fields.get("issuer") and bool(fields.get("subject"))
    ready = hostname_matches and days_remaining is not None and days_remaining >= 14 and not self_signed
    return {
        "ready": ready,
        "certificate_present": True,
        "hostname_matches": hostname_matches,
        "days_remaining": days_remaining,
        "self_signed": self_signed,
        "subject": fields.get("subject"),
        "issuer": fields.get("issuer"),
        "not_after": fields.get("not_after"),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MailboxDNSMailOps/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print("mail-ops:", fmt % args, flush=True)

    def _authorized(self) -> bool:
        return bool(TOKEN) and self.headers.get("X-Mail-Ops-Token") == TOKEN

    def _json(self, status: int, payload: dict | list) -> None:
        data = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _queue_id(self) -> str | None:
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        if len(parts) == 3 and parts[:2] == ["queue", "items"] and QUEUE_ID_RE.fullmatch(parts[2]):
            return parts[2].rstrip("*!")
        return None

    def do_GET(self) -> None:
        if not self._authorized():
            self._json(401, {"detail": "unauthorized"})
            return
        path = urlparse(self.path).path
        try:
            if path == "/health":
                self._json(200, {"status": "ok"})
            elif path == "/queue":
                self._json(200, {"items": queue_rows()})
            elif path == "/queue/deferred":
                rows = deferred_rows()
                self._json(200, {"items": rows, "total": len(rows)})
            elif path == "/queue/summary":
                rows = queue_rows()
                deferred = sum(1 for row in rows if row.get("delay_reason"))
                self._json(200, {"queued": len(rows), "deferred": deferred})
            elif path == "/tls/status":
                self._json(200, tls_status())
            else:
                self._json(404, {"detail": "not found"})
        except Exception as exc:
            self._json(500, {"detail": str(exc)})

    def do_POST(self) -> None:
        if not self._authorized():
            self._json(401, {"detail": "unauthorized"})
            return
        path = urlparse(self.path).path
        queue_id = self._queue_id()
        try:
            if path == "/queue/flush":
                code, out, err = run_command(["postqueue", "-f"])
                self._json(200 if code == 0 else 500, {"ok": code == 0, "output": (out or err).strip()})
                return
            if queue_id:
                code, out, err = run_command(["postsuper", "-r", queue_id])
                self._json(200 if code == 0 else 404, {"ok": code == 0, "queue_id": queue_id, "output": (out or err).strip()})
                return
            self._json(404, {"detail": "not found"})
        except Exception as exc:
            self._json(500, {"detail": str(exc)})

    def do_DELETE(self) -> None:
        if not self._authorized():
            self._json(401, {"detail": "unauthorized"})
            return
        queue_id = self._queue_id()
        if not queue_id:
            self._json(404, {"detail": "not found"})
            return
        try:
            code, out, err = run_command(["postsuper", "-d", queue_id])
            self._json(200 if code == 0 else 404, {"ok": code == 0, "queue_id": queue_id, "output": (out or err).strip()})
        except Exception as exc:
            self._json(500, {"detail": str(exc)})


if __name__ == "__main__":
    if len(TOKEN) < 24:
        raise SystemExit("MAIL_OPS_TOKEN must be at least 24 characters")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
