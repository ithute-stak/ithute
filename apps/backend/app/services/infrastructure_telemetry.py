from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings


class InfrastructureTelemetryError(RuntimeError):
    pass


def _prometheus(expression: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": expression})
    request = urllib.request.Request(f"{settings.prometheus_url.rstrip('/')}/api/v1/query?{params}")
    try:
        with urllib.request.urlopen(request, timeout=settings.prometheus_timeout_seconds) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise InfrastructureTelemetryError("Live infrastructure telemetry is unavailable") from exc

    if payload.get("status") != "success":
        raise InfrastructureTelemetryError("Prometheus infrastructure query failed")
    result = payload.get("data", {}).get("result", [])
    return result if isinstance(result, list) else []


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _scalar(expression: str) -> float | None:
    rows = _prometheus(expression)
    if not rows:
        return None
    try:
        return _number(rows[0]["value"][1])
    except (KeyError, IndexError, TypeError):
        return None


def _first_scalar(*expressions: str) -> float | None:
    for expression in expressions:
        value = _scalar(expression)
        if value is not None:
            return value
    return None


def _vector(expression: str) -> list[tuple[dict[str, str], float]]:
    output: list[tuple[dict[str, str], float]] = []
    for row in _prometheus(expression):
        try:
            labels = row.get("metric") or {}
            value = _number(row["value"][1])
        except (KeyError, IndexError, TypeError):
            continue
        if not isinstance(labels, dict) or value is None:
            continue
        output.append(({str(key): str(item) for key, item in labels.items()}, value))
    return output


def _pct(used: float | None, total: float | None) -> float | None:
    if used is None or total is None or total <= 0:
        return None
    return round(max(0.0, min(100.0, used / total * 100.0)), 1)


def _rounded(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _container_key(labels: dict[str, str]) -> str:
    for key in ("name", "container", "container_label_com_docker_compose_service"):
        value = labels.get(key, "").strip().lstrip("/")
        if value:
            return value
    container_id = labels.get("id", "").strip().strip("/")
    if not container_id:
        return ""
    leaf = container_id.rsplit("/", 1)[-1]
    if leaf.startswith("docker-") and leaf.endswith(".scope"):
        leaf = leaf[7:-6]
    if leaf.startswith("cri-containerd-") and leaf.endswith(".scope"):
        leaf = leaf[15:-6]
    return leaf[-64:]


def _container_map(expression: str) -> dict[str, tuple[dict[str, str], float]]:
    rows: dict[str, tuple[dict[str, str], float]] = {}
    for labels, value in _vector(expression):
        name = _container_key(labels)
        if not name:
            continue
        previous = rows.get(name)
        if previous is None or value > previous[1]:
            rows[name] = (labels, value)
    return rows


def _runtime_alert(label: str, value: float | None) -> dict[str, str] | None:
    if value is None or value < 80:
        return None
    severity = "critical" if value >= 95 else "warning"
    return {
        "severity": severity,
        "title": f"Physical VPS {label} is {value:.1f}%",
        "detail": "Immediate capacity review is recommended." if severity == "critical" else "Runtime utilisation is approaching the operating reserve.",
    }


def live_infrastructure_telemetry() -> dict[str, Any]:
    cpu_percent = _first_scalar(
        '100 * (1 - avg(irate(node_cpu_seconds_total{mode="idle"}[1m])))',
        '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[2m])))',
    )
    memory_total = _scalar("node_memory_MemTotal_bytes")
    memory_available = _scalar("node_memory_MemAvailable_bytes")
    memory_used = None if memory_total is None or memory_available is None else max(0.0, memory_total - memory_available)
    memory_percent = _pct(memory_used, memory_total)
    disk_total = _scalar('sum(node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|devtmpfs|squashfs|overlay"})')
    disk_available = _scalar('sum(node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|devtmpfs|squashfs|overlay"})')
    disk_used = None if disk_total is None or disk_available is None else max(0.0, disk_total - disk_available)
    disk_percent = _pct(disk_used, disk_total)
    boot_time = _scalar("node_boot_time_seconds")
    node_up = _scalar('up{job="ithute-node"}')
    containers_up = _scalar('up{job="ithute-containers"}')
    now = datetime.now(timezone.utc)

    selector = '{id!="/",id!=""}'
    cpu_by_name = _container_map(f"sum by (name, image, id) (irate(container_cpu_usage_seconds_total{selector}[1m])) * 100")
    if not cpu_by_name:
        cpu_by_name = _container_map(f"sum by (name, image, id) (rate(container_cpu_usage_seconds_total{selector}[2m])) * 100")
    memory_by_name = _container_map(f"sum by (name, image, id) (container_memory_working_set_bytes{selector})")
    limit_by_name = _container_map(f"sum by (name, image, id) (container_spec_memory_limit_bytes{selector})")
    rx_by_name = _container_map(f"sum by (name, image, id) (irate(container_network_receive_bytes_total{selector}[1m]))")
    tx_by_name = _container_map(f"sum by (name, image, id) (irate(container_network_transmit_bytes_total{selector}[1m]))")

    container_names = set(cpu_by_name) | set(memory_by_name) | set(rx_by_name) | set(tx_by_name)
    containers: list[dict[str, Any]] = []
    for name in container_names:
        cpu_row = cpu_by_name.get(name)
        memory_row = memory_by_name.get(name)
        limit_row = limit_by_name.get(name)
        labels = (cpu_row or memory_row or rx_by_name.get(name) or tx_by_name.get(name) or ({}, 0.0))[0]
        memory = memory_row[1] if memory_row else None
        limit = limit_row[1] if limit_row else None
        finite_limit = limit if limit is not None and 0 < limit < 9e18 else None
        containers.append(
            {
                "name": name,
                "image": labels.get("image") or None,
                "cpu_percent": _rounded(cpu_row[1], 2) if cpu_row else None,
                "memory_bytes": int(memory) if memory is not None else None,
                "memory_limit_bytes": int(finite_limit) if finite_limit is not None else None,
                "memory_percent": _pct(memory, finite_limit),
                "network_receive_bytes_per_second": _rounded(rx_by_name[name][1], 1) if name in rx_by_name else None,
                "network_transmit_bytes_per_second": _rounded(tx_by_name[name][1], 1) if name in tx_by_name else None,
            }
        )
    containers.sort(key=lambda item: ((item["cpu_percent"] or 0.0), (item["memory_bytes"] or 0)), reverse=True)

    host_values = (cpu_percent, memory_total, disk_total)
    available_count = sum(value is not None for value in host_values)
    alerts = [item for item in (_runtime_alert("CPU", cpu_percent), _runtime_alert("memory", memory_percent), _runtime_alert("disk", disk_percent)) if item]
    if node_up is not None and node_up < 1:
        alerts.append({"severity": "critical", "title": "Node exporter is down", "detail": "Physical host metrics cannot be trusted until the collector recovers."})
    if containers_up is not None and containers_up < 1:
        alerts.append({"severity": "warning", "title": "Container collector is down", "detail": "Docker resource metrics are temporarily unavailable."})
    if containers_up is not None and containers_up >= 1 and not containers:
        alerts.append({"severity": "warning", "title": "Container collector has no workload samples", "detail": "cAdvisor is reachable, but container CPU/memory samples have not populated yet."})

    if not available_count:
        status = "unavailable"
    elif available_count < len(host_values):
        status = "partial"
    elif any(item["severity"] == "critical" for item in alerts):
        status = "critical"
    elif alerts:
        status = "warning"
    else:
        status = "ok"

    return {
        "status": status,
        "sampled_at": now.isoformat(),
        "collectors": {
            "node_exporter": "up" if node_up is not None and node_up >= 1 else ("down" if node_up is not None else "unknown"),
            "cadvisor": "up" if containers_up is not None and containers_up >= 1 else ("down" if containers_up is not None else "unknown"),
        },
        "alerts": alerts,
        "host": {
            "cpu_percent": _rounded(cpu_percent, 1),
            "load_1m": _rounded(_scalar("node_load1"), 2),
            "load_5m": _rounded(_scalar("node_load5"), 2),
            "load_15m": _rounded(_scalar("node_load15"), 2),
            "memory_total_bytes": int(memory_total) if memory_total is not None else None,
            "memory_used_bytes": int(memory_used) if memory_used is not None else None,
            "memory_percent": memory_percent,
            "disk_total_bytes": int(disk_total) if disk_total is not None else None,
            "disk_used_bytes": int(disk_used) if disk_used is not None else None,
            "disk_percent": disk_percent,
            "disk_read_bytes_per_second": _rounded(_first_scalar('sum(irate(node_disk_read_bytes_total{device!~"loop.*|ram.*"}[1m]))', 'sum(rate(node_disk_read_bytes_total{device!~"loop.*|ram.*"}[2m]))'), 1),
            "disk_write_bytes_per_second": _rounded(_first_scalar('sum(irate(node_disk_written_bytes_total{device!~"loop.*|ram.*"}[1m]))', 'sum(rate(node_disk_written_bytes_total{device!~"loop.*|ram.*"}[2m]))'), 1),
            "network_receive_bytes_per_second": _rounded(_first_scalar('sum(irate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[1m]))', 'sum(rate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[2m]))'), 1),
            "network_transmit_bytes_per_second": _rounded(_first_scalar('sum(irate(node_network_transmit_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[1m]))', 'sum(rate(node_network_transmit_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[2m]))'), 1),
            "uptime_seconds": int(max(0.0, now.timestamp() - boot_time)) if boot_time is not None else None,
        },
        "containers": containers[:40],
        "container_count": len(containers),
    }
