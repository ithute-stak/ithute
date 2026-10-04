#!/usr/bin/env python3
"""Ithute hosting-node agent v3.

This remains one privileged host process. It reuses the proven deployment and
shared-database implementation from agent.py and adds a narrow project-runtime
operations queue for restart and bounded log snapshots.
"""

from __future__ import annotations

import signal
import time
import uuid
from typing import Any

import agent as base

AGENT_VERSION = "ithute-hosting-agent/3"
MAX_LOG_CHARS = 240_000

# Ensure API requests made through the shared implementation advertise v3.
base.AGENT_VERSION = AGENT_VERSION


def _project_names(project_id: str) -> tuple[str, str]:
    try:
        parsed = uuid.UUID(project_id)
    except (ValueError, AttributeError) as exc:
        raise RuntimeError("Project operation contains an invalid project id") from exc
    key = parsed.hex
    return f"ithute-hosted-{key}", f"ithute-project-{key[:16]}"


def claim_project_operation() -> dict[str, Any] | None:
    result = base.api("/hosting/agent/project-operations/claim")
    work = result.get("operation")
    return work if isinstance(work, dict) else None


def report_project_operation(
    operation_id: str,
    success: bool,
    *,
    output: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    return base.api(
        f"/hosting/agent/project-operations/{operation_id}/status",
        {"success": success, "output": output, "message": message},
    )


def process_project_operation(work: dict[str, Any]) -> None:
    operation_id = str(work.get("id") or "")
    operation = str(work.get("operation") or "")
    project = work.get("project")
    if not operation_id:
        raise RuntimeError("Project operation is missing its id")
    if operation not in {"restart", "logs", "retire"}:
        raise RuntimeError("Unknown project runtime operation")
    if not isinstance(project, dict):
        raise RuntimeError("Project operation is missing its project manifest")

    project_id = str(project.get("id") or "")
    container, network = _project_names(project_id)
    volume = f"ithute-project-{uuid.UUID(project_id).hex}-data"

    if operation == "retire":
        if project.get("discard_local_data") is not True:
            raise RuntimeError("Retire operation is missing the explicit disposable-data contract")
        stale_ids = base.docker(
            "ps", "-aq", "--filter", f"label=ithute.project={project_id}", check=False
        ).stdout.splitlines()
        for container_id in stale_ids:
            container_id = container_id.strip()
            if container_id:
                base.docker("rm", "-f", container_id)
        if base.exists("network", network):
            base.docker("network", "rm", network, check=False)
        if base.exists("volume", volume):
            base.docker("volume", "rm", "-f", volume)
        report_project_operation(operation_id, True, message="Stale source placement and disposable local data removed")
        base.log(f"project operation {operation_id} retire complete")
        return

    if not base.exists("container", container):
        raise RuntimeError("Hosted project container is not present on this node")

    if operation == "restart":
        if str(project.get("status") or "") != "running":
            raise RuntimeError("Only a running hosted project can be restarted")
        port = int(project.get("container_port") or 0)
        health_path = str(project.get("health_path") or "")
        if not 1024 <= port <= 65535:
            raise RuntimeError("Project restart manifest contains an invalid port")
        if not health_path.startswith("/") or "\r" in health_path or "\n" in health_path:
            raise RuntimeError("Project restart manifest contains an invalid health path")
        base.docker("restart", "--time", "20", container, timeout=60)
        ip = base.private_ip(container, network)
        base.wait_healthy(ip, port, health_path)
        report_project_operation(operation_id, True, message="Container restarted and private health check passed")
        base.log(f"project operation {operation_id} restart complete")
        return

    lines = int(work.get("requested_lines") or 300)
    if not 1 <= lines <= 2000:
        raise RuntimeError("Project log request exceeds allowed line limits")
    result = base.docker("logs", "--tail", str(lines), "--timestamps", container, check=False, timeout=30)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise RuntimeError(f"docker logs failed: {detail}")
    # Docker may write application log streams to stdout and/or stderr. Preserve
    # both but enforce a bounded payload before it reaches the control plane.
    combined = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    report_project_operation(operation_id, True, output=combined[-MAX_LOG_CHARS:])
    base.log(f"project operation {operation_id} logs complete")


def safe_process_project_operation(work: dict[str, Any]) -> None:
    operation_id = str(work.get("id") or "")
    try:
        process_project_operation(work)
    except Exception as exc:
        error = str(exc)[:1900]
        base.log(f"project operation {operation_id or '<unknown>'} failed: {error}")
        if operation_id:
            try:
                report_project_operation(operation_id, False, message=error)
            except Exception as report_exc:
                base.log(f"could not report project operation failure: {report_exc}")


def handle_signal(signum: int, frame: Any) -> None:
    base.handle_signal(signum, frame)


def main() -> int:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    base.docker("version", "--format", "{{.Server.Version}}")
    base.log(f"starting {AGENT_VERSION}")
    last_heartbeat = 0.0
    while not base.STOP:
        now = time.monotonic()
        try:
            if now - last_heartbeat >= base.HEARTBEAT_SECONDS:
                base.heartbeat()
                last_heartbeat = now

            database_work = base.claim_database()
            if database_work:
                base.process_database(database_work)
                continue

            project_work = claim_project_operation()
            if project_work:
                safe_process_project_operation(project_work)
                continue

            deployment_work = base.claim()
            if deployment_work:
                base.activate(deployment_work)
                continue
        except Exception as exc:
            base.log(f"poll failed: {exc}")

        for _ in range(base.POLL_SECONDS):
            if base.STOP:
                break
            time.sleep(1)

    base.log("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
