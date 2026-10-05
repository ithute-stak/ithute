#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENT_VERSION = "ithute-server-agent/2"
API_URL = os.getenv("ITHUTE_API_URL", "https://ithute.co.ls/api/v1").rstrip("/")
TOKEN = os.getenv("ITHUTE_SERVER_AGENT_TOKEN", "").strip()
INTERVAL = max(30, int(os.getenv("ITHUTE_SERVER_AGENT_INTERVAL", "60")))
TIMEOUT = max(3, int(os.getenv("ITHUTE_SERVER_AGENT_TIMEOUT", "10")))
SERVICE_RE = re.compile(r"^[A-Za-z0-9@_.:-]+(?:\.service)?$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
BLOCKED_SERVICES = {
    "ssh", "sshd", "ssh.service", "sshd.service",
    "networking", "networking.service",
    "systemd-networkd", "systemd-networkd.service",
    "ufw", "ufw.service", "firewalld", "firewalld.service",
}


def read_text(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def cpu_percent() -> float | None:
    def sample():
        raw = read_text("/proc/stat").splitlines()
        if not raw:
            return None
        parts = raw[0].split()
        if not parts or parts[0] != "cpu":
            return None
        values = [int(x) for x in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return total, idle
    first = sample()
    if first is None:
        return None
    time.sleep(0.2)
    second = sample()
    if second is None:
        return None
    total_delta = second[0] - first[0]
    idle_delta = second[1] - first[1]
    if total_delta <= 0:
        return None
    return round(100.0 * (1.0 - idle_delta / total_delta), 1)


def memory() -> dict:
    values = {}
    for line in read_text("/proc/meminfo").splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        try:
            values[key] = int(rest.strip().split()[0]) * 1024
        except (ValueError, IndexError):
            pass
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    used = max(0, total - available)
    return {"total_bytes": total, "used_bytes": used, "available_bytes": available, "used_percent": round((used / total) * 100, 1) if total else None}


def disks() -> list[dict]:
    result = []
    mounts = []
    for line in read_text("/proc/mounts").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mountpoint, fstype = parts[:3]
        if not device.startswith("/dev/"):
            continue
        if mountpoint in mounts:
            continue
        mounts.append(mountpoint)
        try:
            usage = shutil.disk_usage(mountpoint)
        except OSError:
            continue
        result.append({
            "device": device,
            "mountpoint": mountpoint,
            "filesystem": fstype,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else None,
        })
    return result


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def command_output(args: list[str], timeout: int = 3) -> str | None:
    try:
        completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def service_active(name: str) -> bool:
    if not command_exists("systemctl"):
        return False
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", name], timeout=3, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def docker_info() -> dict:
    if not command_exists("docker"):
        return {"installed": False, "reachable": False, "version": None, "containers_running": 0, "containers_total": 0, "containers": []}
    version = command_output(["docker", "version", "--format", "{{.Server.Version}}"])
    inventory = command_output([
        "docker", "ps", "-a",
        "--format", '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Label "ithute.project_id"}}',
    ], timeout=8)
    containers: list[dict] = []
    if inventory:
        for line in inventory.splitlines()[:1000]:
            parts = line.split("\t", 4)
            if len(parts) < 4:
                continue
            project_id = parts[4].strip() if len(parts) > 4 else ""
            containers.append({
                "id": parts[0].strip(),
                "name": parts[1].strip(),
                "image": parts[2].strip(),
                "state": parts[3].strip().lower(),
                "labels": {"ithute.project_id": project_id} if project_id else {},
            })
    return {
        "installed": True,
        "reachable": version is not None,
        "version": version,
        "containers_total": len(containers),
        "containers_running": sum(1 for item in containers if item.get("state") == "running"),
        "containers": containers,
    }


def wireguard_info() -> dict:
    if not command_exists("wg") or not command_exists("ip"):
        return {"installed": False, "interface": "ithute0", "up": False, "connected": False}
    public_key = command_output(["wg", "show", "ithute0", "public-key"])
    addresses = command_output(["ip", "-4", "-o", "addr", "show", "dev", "ithute0"])
    latest = command_output(["wg", "show", "ithute0", "latest-handshakes"])
    transfer = command_output(["wg", "show", "ithute0", "transfer"])
    handshake_unix = 0
    peer_key = None
    if latest:
        row = latest.splitlines()[0].split()
        if len(row) >= 2:
            peer_key = row[0]
            try:
                handshake_unix = int(row[1])
            except ValueError:
                handshake_unix = 0
    rx_bytes = tx_bytes = None
    if transfer:
        row = transfer.splitlines()[0].split()
        if len(row) >= 3:
            try:
                rx_bytes = int(row[1])
                tx_bytes = int(row[2])
            except ValueError:
                pass
    address = None
    if addresses:
        parts = addresses.split()
        if "inet" in parts:
            try:
                address = parts[parts.index("inet") + 1].split("/", 1)[0]
            except (ValueError, IndexError):
                pass
    now = int(time.time())
    return {
        "installed": True,
        "interface": "ithute0",
        "up": bool(public_key and address),
        "connected": bool(handshake_unix and now - handshake_unix <= 180),
        "public_key": public_key,
        "peer_public_key": peer_key,
        "address": address,
        "latest_handshake_unix": handshake_unix or None,
        "rx_bytes": rx_bytes,
        "tx_bytes": tx_bytes,
    }


def capabilities() -> dict:
    return {
        "docker": command_exists("docker"),
        "postgresql": command_exists("psql") or service_active("postgresql"),
        "mysql": command_exists("mysql") or service_active("mysql") or service_active("mariadb"),
        "mariadb": command_exists("mariadb") or service_active("mariadb"),
        "mongodb": command_exists("mongosh") or service_active("mongod"),
        "redis": command_exists("redis-cli") or service_active("redis") or service_active("redis-server"),
        "mail": service_active("postfix") or command_exists("postfix"),
        "imap": service_active("dovecot") or command_exists("dovecot"),
        "systemd": command_exists("systemctl"),
        "wireguard": command_exists("wg"),
        "structured_commands": command_exists("systemctl") or command_exists("docker"),
        "container_inventory": command_exists("docker"),
    }


def uptime_seconds() -> int | None:
    try:
        return int(float(read_text("/proc/uptime").split()[0]))
    except (ValueError, IndexError):
        return None


def payload() -> dict:
    return {
        "version": AGENT_VERSION,
        "os_name": f"{platform.system()} {platform.release()}".strip(),
        "kernel_version": platform.version()[:160],
        "uptime_seconds": uptime_seconds(),
        "telemetry": {
            "hostname": socket.gethostname(),
            "cpu": {"used_percent": cpu_percent(), "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None},
            "memory": memory(),
            "disks": disks(),
            "docker": docker_info(),
            "wireguard": wireguard_info(),
        },
        "capabilities": capabilities(),
    }


def api_json(path: str, *, method: str = "POST", body: dict | None = None) -> dict:
    if not TOKEN:
        raise RuntimeError("ITHUTE_SERVER_AGENT_TOKEN is required")
    raw = json.dumps(body or {}).encode("utf-8")
    request = urllib.request.Request(
        f"{API_URL}{path}",
        data=raw,
        headers={"Content-Type": "application/json", "X-Ithute-Server-Agent": TOKEN},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"agent API failed with HTTP {response.status}")
        payload_raw = response.read()
    return json.loads(payload_raw.decode("utf-8")) if payload_raw else {}


def execute_structured_command(command: dict) -> tuple[bool, dict, str | None]:
    kind = str(command.get("kind") or "")
    payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
    if kind == "agent.ping":
        return True, {"pong": True, "hostname": socket.gethostname(), "version": AGENT_VERSION}, None

    if kind.startswith("service."):
        unit = str(payload.get("unit") or "").strip()
        verb = kind.split(".", 1)[1]
        if verb not in {"start", "stop", "restart"}:
            return False, {}, "unsupported service action"
        normalized = unit if unit.endswith(".service") else f"{unit}.service"
        if not SERVICE_RE.fullmatch(unit) or unit in BLOCKED_SERVICES or normalized in BLOCKED_SERVICES:
            return False, {}, "service action rejected by local agent policy"
        unit = normalized
        try:
            completed = subprocess.run(
                ["systemctl", verb, unit],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, {}, str(exc)[:8000]
        output = (completed.stdout or "")[-4000:]
        return completed.returncode == 0, {"unit": unit, "action": verb, "output": output}, None if completed.returncode == 0 else output

    if kind.startswith("container."):
        container = str(payload.get("container") or "").strip()
        verb = kind.split(".", 1)[1]
        if verb not in {"start", "stop", "restart"}:
            return False, {}, "unsupported container action"
        if not CONTAINER_RE.fullmatch(container):
            return False, {}, "container action rejected by local agent policy"
        try:
            completed = subprocess.run(
                ["docker", verb, container],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, {}, str(exc)[:8000]
        output = (completed.stdout or "")[-4000:]
        return completed.returncode == 0, {"container": container, "action": verb, "output": output}, None if completed.returncode == 0 else output
    return False, {}, "unsupported structured command"


def poll_command() -> None:
    body = api_json("/platform/infrastructure/agent/commands/next")
    command = body.get("command") if isinstance(body, dict) else None
    if not isinstance(command, dict):
        return
    command_id = str(command.get("id") or "")
    if not command_id:
        return
    ok, result, error = execute_structured_command(command)
    api_json(
        f"/platform/infrastructure/agent/commands/{command_id}/result",
        body={"ok": ok, "result": result, "error": error},
    )


def heartbeat() -> None:
    if not TOKEN:
        raise RuntimeError("ITHUTE_SERVER_AGENT_TOKEN is required")
    body = json.dumps(payload()).encode("utf-8")
    request = urllib.request.Request(
        f"{API_URL}/platform/infrastructure/agent/heartbeat",
        data=body,
        headers={"Content-Type": "application/json", "X-Ithute-Server-Agent": TOKEN},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"heartbeat failed with HTTP {response.status}")


def main() -> int:
    print(f"starting {AGENT_VERSION}", flush=True)
    while True:
        try:
            heartbeat()
            poll_command()
        except Exception as exc:
            print(f"agent cycle failed: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
