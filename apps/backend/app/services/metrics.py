from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "mailbox_dns_http_requests_total",
    "HTTP requests handled by the control plane",
    ["method", "route", "status"],
)
HTTP_LATENCY = Histogram(
    "mailbox_dns_http_request_duration_seconds",
    "HTTP request latency for the control plane",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
READINESS = Gauge(
    "mailbox_dns_dependency_ready",
    "Dependency readiness state (1 ready, 0 unavailable)",
    ["dependency"],
)
BACKUP_HEALTH = Gauge(
    "mailbox_dns_backup_healthy",
    "Latest backup freshness/health state (1 healthy, 0 unhealthy)",
)


def normalized_route(request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path
