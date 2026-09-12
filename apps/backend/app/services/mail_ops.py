import json
import urllib.error
import urllib.request

from app.core.config import settings


class MailOpsError(RuntimeError):
    pass


def _request(path: str, method: str = "GET") -> dict:
    req = urllib.request.Request(
        f"{settings.mail_ops_url.rstrip('/')}{path}",
        method=method,
        headers={"X-Mail-Ops-Token": settings.mail_ops_token},
    )
    try:
        with urllib.request.urlopen(req, timeout=settings.mail_ops_timeout_seconds) as response:
            body = response.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise MailOpsError(f"mail operations returned HTTP {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise MailOpsError("mail operations service is unavailable") from exc


def queue_list() -> dict:
    return _request("/queue")


def queue_deferred() -> dict:
    return _request("/queue/deferred")


def queue_summary() -> dict:
    return _request("/queue/summary")


def tls_status() -> dict:
    return _request("/tls/status")


def queue_flush() -> dict:
    return _request("/queue/flush", "POST")


def queue_retry(queue_id: str) -> dict:
    return _request(f"/queue/items/{queue_id}", "POST")


def queue_delete(queue_id: str) -> dict:
    return _request(f"/queue/items/{queue_id}", "DELETE")
