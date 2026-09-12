import json
import urllib.error
import urllib.parse
import urllib.request

from app.core.config import settings


class OperationsStatusError(RuntimeError):
    pass


def _query(expression: str) -> float | None:
    params = urllib.parse.urlencode({"query": expression})
    request = urllib.request.Request(f"{settings.prometheus_url.rstrip('/')}/api/v1/query?{params}")
    try:
        with urllib.request.urlopen(request, timeout=settings.prometheus_timeout_seconds) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OperationsStatusError("Prometheus operations telemetry is unavailable") from exc

    if payload.get("status") != "success":
        raise OperationsStatusError("Prometheus query failed")
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    try:
        return float(result[0]["value"][1])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise OperationsStatusError("Prometheus returned an invalid query result") from exc


def _state(value: float | None) -> str:
    if value is None:
        return "unknown"
    return "ok" if value >= 1 else "down"


def operations_status() -> dict:
    backend = _query('up{job="mailbox-dns-backend"}')
    smtp = _query('probe_success{job="smtp-synthetic"}')
    imap = _query('probe_success{job="imap-synthetic"}')
    dns = _query('probe_success{job="dns-synthetic"}')
    queue_total = _query("mailbox_dns_mail_queue_total")
    backup_success = _query("mailbox_dns_backup_last_run_success")
    return {
        "status": "ok" if all(v is not None and v >= 1 for v in (backend, smtp, imap, dns, backup_success)) else "degraded",
        "services": {
            "backend": _state(backend),
            "smtp": _state(smtp),
            "imap": _state(imap),
            "authoritative_dns": _state(dns),
            "backup": _state(backup_success),
        },
        "mail_queue_total": int(queue_total) if queue_total is not None else None,
    }


def slo_status() -> dict:
    target = settings.operations_slo_target
    availability = _query("mailbox_dns:slo_availability_7d")
    error_budget_remaining = _query("mailbox_dns:slo_error_budget_remaining_7d")
    burn_rate_1h = _query("mailbox_dns:slo_burn_rate_1h")
    return {
        "window": "7d",
        "target": target,
        "availability": availability,
        "error_budget_fraction": 1.0 - target,
        "error_budget_remaining": error_budget_remaining,
        "burn_rate_1h": burn_rate_1h,
        "status": "unknown" if availability is None else ("meeting" if availability >= target else "breached"),
    }
