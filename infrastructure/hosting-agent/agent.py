#!/usr/bin/env python3
"""Ithute managed-hosting node agent.

The public API never receives Docker access. This host-side agent polls for
pre-approved, digest-pinned deployment work and activates only images that are
already present on the node. Image building/pulling is deliberately outside
this process so production nodes never execute customer build scripts.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENT_VERSION = "ithute-hosting-agent/1"
STOP = False


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


API_URL = env("ITHUTE_API_URL").rstrip("/")
NODE_ID = env("ITHUTE_HOSTING_NODE_ID")
AGENT_TOKEN = env("ITHUTE_HOSTING_AGENT_TOKEN")
POLL_SECONDS = max(5, int(os.getenv("ITHUTE_HOSTING_POLL_SECONDS", "15")))
DOCKER = os.getenv("ITHUTE_HOSTING_DOCKER", "docker")
ALLOW_HTTP = os.getenv("ITHUTE_HOSTING_ALLOW_HTTP", "false").lower() == "true"

if not API_URL.startswith("https://") and not ALLOW_HTTP:
    raise RuntimeError("ITHUTE_API_URL must use HTTPS unless ITHUTE_HOSTING_ALLOW_HTTP=true")


def log(message: str) -> None:
    print(f"[hosting-agent] {message}", flush=True)


def api(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{API_URL}/api/v1{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Ithute-Agent-Token": AGENT_TOKEN,
            "User-Agent": AGENT_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Control-plane HTTP {exc.code}: {detail}") from exc


def docker(*args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [DOCKER, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"docker {' '.join(args[:3])} failed: {detail}")
    return result


def exists(kind: str, name: str) -> bool:
    return docker(kind, "inspect", name, check=False).returncode == 0


def validate_image(image_ref: str) -> None:
    if "@sha256:" not in image_ref or not image_ref.startswith("ghcr.io/ithute-stak/hosted-"):
        raise RuntimeError("Refusing image outside approved digest-pinned Ithute hosting namespace")
    if docker("image", "inspect", image_ref, check=False).returncode != 0:
        raise RuntimeError("Approved image is not preloaded on this node; the isolated builder/transfer stage must load it first")
    user = docker("image", "inspect", "--format", "{{.Config.User}}", image_ref).stdout.strip().lower()
    if not user or user in {"0", "root", "0:0", "root:root"}:
        raise RuntimeError("Hosted image must declare a non-root USER")


def ensure_network(name: str, project_id: str) -> None:
    if not exists("network", name):
        docker(
            "network",
            "create",
            "--driver",
            "bridge",
            "--label",
            "ithute.hosted=true",
            "--label",
            f"ithute.project={project_id}",
            name,
        )


def ensure_volume(name: str, project_id: str) -> None:
    if not exists("volume", name):
        docker(
            "volume",
            "create",
            "--label",
            "ithute.hosted=true",
            "--label",
            f"ithute.project={project_id}",
            name,
        )


def container_ip(name: str, network: str) -> str:
    template = "{{(index .NetworkSettings.Networks \"" + network + "\").IPAddress}}"
    value = docker("inspect", "--format", template, name).stdout.strip()
    if not value:
        raise RuntimeError("Candidate container has no private network address")
    return value


def wait_healthy(ip: str, port: int, health_path: str) -> None:
    url = f"http://{ip}:{port}{health_path}"
    last_error = "health endpoint did not respond"
    for _ in range(30):
        if STOP:
            raise RuntimeError("Agent is stopping")
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if 200 <= response.status < 400:
                    return
                last_error = f"health endpoint returned HTTP {response.status}"
        except Exception as exc:  # container may still be starting
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"Candidate failed health check: {last_error}")


def report(deployment_id: str, status: str, *, message: str | None = None, error: str | None = None) -> None:
    api(
        f"/hosting-agent/nodes/{NODE_ID}/deployments/{deployment_id}/report",
        {"status": status, "message": message, "error": error},
    )


def activate(work: dict) -> None:
    deployment_id = work["id"]
    project_id = work["project_id"]
    image_ref = work["image_ref"]
    runtime = work["runtime"]
    current = runtime["container_name"]
    candidate = f"{current}-candidate-{deployment_id.replace('-', '')[:8]}"
    project_key = project_id.replace("-", "")
    network = f"ithute-project-{project_key[:16]}"
    volume = f"ithute-project-{project_key}-data"
    previous_exists = exists("container", current)

    report(deployment_id, "deploying", message="Runtime agent accepted deployment")
    try:
        validate_image(image_ref)
        ensure_network(network, project_id)
        ensure_volume(volume, project_id)

        if exists("container", candidate):
            docker("rm", "-f", candidate)
        if previous_exists:
            docker("stop", "--time", "20", current, timeout=45)

        cpus = max(0.1, int(runtime["cpu_millicores"]) / 1000.0)
        docker(
            "run",
            "-d",
            "--name",
            candidate,
            "--network",
            network,
            "--restart",
            "unless-stopped",
            "--memory",
            f"{int(runtime['memory_mb'])}m",
            "--cpus",
            f"{cpus:.3f}",
            "--pids-limit",
            str(int(runtime["pid_limit"])),
            "--read-only",
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--mount",
            f"type=volume,source={volume},target=/data",
            "--label",
            "ithute.hosted=true",
            "--label",
            f"ithute.project={project_id}",
            "--label",
            f"ithute.deployment={deployment_id}",
            image_ref,
            timeout=180,
        )

        ip = container_ip(candidate, network)
        wait_healthy(ip, int(runtime["container_port"]), runtime["health_path"])

        if previous_exists:
            docker("rm", "-f", current)
        docker("rename", candidate, current)
        report(deployment_id, "healthy", message="Candidate passed private health check and was promoted")
        log(f"deployment {deployment_id} healthy")
    except Exception as exc:
        error = str(exc)[:4000]
        log(f"deployment {deployment_id} failed: {error}")
        if exists("container", candidate):
            docker("rm", "-f", candidate, check=False)
        if previous_exists and exists("container", current):
            docker("start", current, check=False)
        try:
            report(deployment_id, "failed", error=error)
        except Exception as report_exc:
            log(f"could not report failure: {report_exc}")


def claim() -> dict | None:
    payload = api(f"/hosting-agent/nodes/{NODE_ID}/claim", {"agent_version": AGENT_VERSION})
    return payload.get("deployment")


def handle_signal(signum, _frame) -> None:
    global STOP
    log(f"received signal {signum}; stopping after current operation")
    STOP = True


def main() -> int:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    log(f"starting {AGENT_VERSION} for node {NODE_ID}")
    docker("version", "--format", "{{.Server.Version}}")
    while not STOP:
        try:
            work = claim()
            if work:
                activate(work)
                continue
        except Exception as exc:
            log(f"poll failed: {exc}")
        for _ in range(POLL_SECONDS):
            if STOP:
                break
            time.sleep(1)
    log("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
