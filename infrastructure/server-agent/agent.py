#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENT_VERSION = "ithute-server-agent/1"
API_URL = os.getenv("ITHUTE_API_URL", "https://ithute.co.ls/api/v1").rstrip("/")
TOKEN = os.getenv("ITHUTE_SERVER_AGENT_TOKEN", "").strip()
INTERVAL = max(30, int(os.getenv("ITHUTE_SERVER_AGENT_INTERVAL", "60")))
TIMEOUT = max(3, int(os.getenv("ITHUTE_SERVER_AGENT_TIMEOUT", "10")))


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
        return {"installed": False, "reachable": False, "version": None, "containers_running": 0, "containers_total": 0}
    version = command_output(["docker", "version", "--format", "{{.Server.Version}}"])
    total_raw = command_output(["docker", "ps", "-aq"])
    running_raw = command_output(["docker", "ps", "-q"])
    return {
        "installed": True,
        "reachable": version is not None,
        "version": version,
        "containers_total": len(total_raw.splitlines()) if total_raw else 0,
        "containers_running": len(running_raw.splitlines()) if running_raw else 0,
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
        },
        "capabilities": capabilities(),
    }


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
        except Exception as exc:
            print(f"heartbeat failed: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
