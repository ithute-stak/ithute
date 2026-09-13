#!/usr/bin/env python3
"""Ithute managed-hosting node runtime agent.

This process is the only component allowed to activate hosted customer images on
an Ithute hosting node. The public API never receives Docker access. The agent
consumes only a server-issued runtime manifest and refuses mutable, root-user,
or non-Ithute images.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

AGENT_VERSION = "ithute-hosting-agent/1"
ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
STOP = False


def required_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


API_URL = required_env("ITHUTE_API_URL").rstrip("/")
AGENT_TOKEN = required_env("ITHUTE_HOSTING_AGENT_TOKEN")
POLL_SECONDS = max(5, int(os.getenv("ITHUTE_HOSTING_POLL_SECONDS", "15")))
HEARTBEAT_SECONDS = max(15, int(os.getenv("ITHUTE_HOSTING_HEARTBEAT_SECONDS", "60")))
DOCKER = os.getenv("ITHUTE_HOSTING_DOCKER", "docker")
IMAGE_PREFIX = os.getenv("ITHUTE_HOSTING_IMAGE_PREFIX", "ghcr.io/ithute-stak/hosted-").strip().lower()
ALLOW_HTTP = os.getenv("ITHUTE_HOSTING_ALLOW_HTTP", "false").lower() == "true"

if not API_URL.startswith("https://") and not ALLOW_HTTP:
    raise RuntimeError("ITHUTE_API_URL must use HTTPS unless ITHUTE_HOSTING_ALLOW_HTTP=true")
if not AGENT_TOKEN.startswith("ith_host_"):
    raise RuntimeError("ITHUTE_HOSTING_AGENT_TOKEN is not a hosting-node credential")
if not IMAGE_PREFIX:
    raise RuntimeError("ITHUTE_HOSTING_IMAGE_PREFIX cannot be empty")


def log(message: str) -> None:
    print(f"[hosting-agent] {message}", flush=True)


def api(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{API_URL}/api/v1{path}",
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Ithute-Hosting-Agent": AGENT_TOKEN,
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


def docker(
    *args: str,
    check: bool = True,
    timeout: int = 120,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if extra_env:
        process_env.update(extra_env)
    result = subprocess.run(
        [DOCKER, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=process_env,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"docker {' '.join(args[:4])} failed: {detail}")
    return result


def exists(kind: str, name: str) -> bool:
    return docker(kind, "inspect", name, check=False).returncode == 0


def validate_manifest(work: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    image_ref = str(work.get("image_ref") or "").strip().lower()
    digest = str(work.get("image_digest") or "").strip().lower()
    if not image_ref.startswith(IMAGE_PREFIX) or "@sha256:" not in image_ref:
        raise RuntimeError("Refusing image outside the approved digest-pinned Ithute hosting namespace")
    actual_digest = "sha256:" + image_ref.rsplit("@sha256:", 1)[1]
    if not DIGEST_RE.fullmatch(actual_digest) or actual_digest != digest:
        raise RuntimeError("Runtime manifest image digest does not match the immutable image reference")

    project = work.get("project")
    if not isinstance(project, dict):
        raise RuntimeError("Runtime manifest is missing project settings")
    security = project.get("security")
    if not isinstance(security, dict):
        raise RuntimeError("Runtime manifest is missing the security contract")
    if security.get("privileged") is not False:
        raise RuntimeError("Refusing privileged hosted workload")
    if security.get("docker_socket") is not False:
        raise RuntimeError("Refusing hosted workload with Docker socket access")
    if security.get("host_ports") != []:
        raise RuntimeError("Refusing hosted workload that requests public host ports")
    if security.get("no_new_privileges") is not True:
        raise RuntimeError("Runtime manifest must require no-new-privileges")
    if security.get("read_only_root") is not True:
        raise RuntimeError("Runtime manifest must require a read-only root filesystem")
    if "ALL" not in list(security.get("cap_drop") or []):
        raise RuntimeError("Runtime manifest must drop all Linux capabilities")
    if security.get("persistent_mount") != "/data":
        raise RuntimeError("Runtime manifest persistent mount must be /data")

    resources = project.get("resources")
    if not isinstance(resources, dict):
        raise RuntimeError("Runtime manifest is missing resource limits")
    for key in ("storage_mb", "memory_mb", "cpu_millicores", "pid_limit"):
        if int(resources.get(key) or 0) <= 0:
            raise RuntimeError(f"Runtime manifest has an invalid {key} limit")

    environment = project.get("environment") or {}
    if not isinstance(environment, dict):
        raise RuntimeError("Runtime environment must be an object")
    clean_environment: dict[str, str] = {}
    for key, value in environment.items():
        if not ENV_KEY_RE.fullmatch(str(key)):
            raise RuntimeError("Runtime environment contains an invalid key")
        if not isinstance(value, str) or "\x00" in value:
            raise RuntimeError(f"Runtime environment value for {key} is invalid")
        clean_environment[str(key)] = value

    if docker("image", "inspect", image_ref, check=False).returncode != 0:
        raise RuntimeError("Approved image is not preloaded on this node; the isolated builder/transfer stage must load it first")
    image_user = docker("image", "inspect", "--format", "{{.Config.User}}", image_ref).stdout.strip().lower()
    if not image_user or image_user in {"0", "root", "0:0", "root:root"}:
        raise RuntimeError("Hosted image must declare a non-root USER")
    return project, clean_environment


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


def private_ip(container: str, network: str) -> str:
    template = "{{(index .NetworkSettings.Networks \"" + network + "\").IPAddress}}"
    ip = docker("inspect", "--format", template, container).stdout.strip()
    if not ip:
        raise RuntimeError("Candidate container has no private network address")
    return ip


def wait_healthy(ip: str, port: int, path: str) -> None:
    if not path.startswith("/"):
        raise RuntimeError("Health path must start with /")
    url = f"http://{ip}:{port}{path}"
    last_error = "health endpoint did not respond"
    for _ in range(30):
        if STOP:
            raise RuntimeError("Agent is stopping")
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if 200 <= response.status < 400:
                    return
                last_error = f"HTTP {response.status}"
        except Exception as exc:  # the application may still be starting
            last_error = str(exc)
        time.sleep(2)
    raise RuntimeError(f"Candidate failed private health check: {last_error}")


def report(deployment_id: str, status: str, message: str | None = None) -> dict[str, Any]:
    return api(
        f"/hosting/agent/deployments/{deployment_id}/status",
        {"status": status, "message": message},
    )


def restore_previous(current: str, backup: str) -> None:
    if exists("container", current):
        docker("rm", "-f", current, check=False)
    if exists("container", backup):
        docker("rename", backup, current, check=False)
        docker("start", current, check=False)


def activate(work: dict[str, Any]) -> None:
    deployment_id = str(work["id"])
    project, environment = validate_manifest(work)
    project_id = str(project["id"])
    project_key = project_id.replace("-", "")
    current = f"ithute-hosted-{project_key}"
    backup = f"{current}-previous-{deployment_id.replace('-', '')[:8]}"
    network = f"ithute-project-{project_key[:16]}"
    volume = f"ithute-project-{project_key}-data"
    image_ref = str(work["image_ref"])
    resources = project["resources"]
    previous_exists = exists("container", current)

    try:
        ensure_network(network, project_id)
        ensure_volume(volume, project_id)
        if exists("container", backup):
            docker("rm", "-f", backup)
        if previous_exists:
            docker("stop", "--time", "20", current, timeout=45)
            docker("rename", current, backup)

        cpus = max(0.1, int(resources["cpu_millicores"]) / 1000.0)
        env_args: list[str] = []
        for key in sorted(environment):
            env_args.extend(["--env", key])

        docker(
            "run",
            "-d",
            "--name",
            current,
            "--network",
            network,
            "--restart",
            "unless-stopped",
            "--memory",
            f"{int(resources['memory_mb'])}m",
            "--cpus",
            f"{cpus:.3f}",
            "--pids-limit",
            str(int(resources["pid_limit"])),
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
            *env_args,
            image_ref,
            timeout=180,
            extra_env=environment,
        )
        report(deployment_id, "running", "Candidate container started on its private project network")
        ip = private_ip(current, network)
        wait_healthy(ip, int(project["container_port"]), str(project["health_path"]))

        # Control-plane acknowledgement is part of promotion. If it cannot be
        # committed, restore the previous release instead of drifting silently.
        report(deployment_id, "healthy", "Private health check passed; release promoted")
        if exists("container", backup):
            docker("rm", "-f", backup)
        log(f"deployment {deployment_id} healthy")
    except Exception as exc:
        error = str(exc)[:1900]
        log(f"deployment {deployment_id} failed: {error}")
        restore_previous(current, backup)
        try:
            report(deployment_id, "failed", error)
        except Exception as report_exc:
            log(f"could not report deployment failure: {report_exc}")


def heartbeat() -> None:
    api("/hosting/agent/heartbeat", {"version": AGENT_VERSION})


def claim() -> dict[str, Any] | None:
    result = api("/hosting/agent/deployments/claim")
    work = result.get("deployment")
    return work if isinstance(work, dict) else None


def handle_signal(signum: int, _frame: Any) -> None:
    global STOP
    log(f"received signal {signum}; stopping after current operation")
    STOP = True


def main() -> int:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    docker("version", "--format", "{{.Server.Version}}")
    log(f"starting {AGENT_VERSION}")
    last_heartbeat = 0.0
    while not STOP:
        now = time.monotonic()
        try:
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                heartbeat()
                last_heartbeat = now
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
