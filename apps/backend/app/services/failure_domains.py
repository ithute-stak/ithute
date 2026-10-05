from __future__ import annotations

from app.models import InfrastructureServer


FAILURE_DOMAIN_LEVELS = (
    "provider",
    "region",
    "datacenter",
    "physical_host",
    "network_segment",
)

FAILURE_DOMAIN_PENALTIES = {
    "provider": 5.0,
    "region": 15.0,
    "datacenter": 30.0,
    "physical_host": 60.0,
    "network_segment": 40.0,
}


def failure_domain_values(server: InfrastructureServer | None) -> dict[str, str | None]:
    if server is None:
        return {level: None for level in FAILURE_DOMAIN_LEVELS}
    values = {
        "provider": server.provider,
        "region": server.region,
        "datacenter": server.datacenter,
        "physical_host": server.physical_host,
        "network_segment": server.network_segment,
    }
    return {
        key: (str(value).strip().lower() if value is not None and str(value).strip() else None)
        for key, value in values.items()
    }


def failure_domain_overlap(
    source: InfrastructureServer | None,
    target: InfrastructureServer | None,
) -> dict:
    source_values = failure_domain_values(source)
    target_values = failure_domain_values(target)
    shared: list[str] = []
    penalty = 0.0
    for level in FAILURE_DOMAIN_LEVELS:
        left = source_values[level]
        right = target_values[level]
        if left is not None and right is not None and left == right:
            shared.append(level)
            penalty += FAILURE_DOMAIN_PENALTIES[level]

    highest_risk = None
    for level in ("physical_host", "network_segment", "datacenter", "region", "provider"):
        if level in shared:
            highest_risk = level
            break

    return {
        "shared": shared,
        "penalty": penalty,
        "highest_risk": highest_risk,
        "source": source_values,
        "target": target_values,
    }


def failure_domain_sort_key(overlap: dict, *, placement_score: float, name: str, node_id: str) -> tuple:
    shared = set(overlap.get("shared") or [])
    hard_collision = any(level in shared for level in ("physical_host", "network_segment"))
    return (
        hard_collision,
        float(overlap.get("penalty") or 0.0),
        float(placement_score),
        str(name or "").lower(),
        str(node_id or ""),
    )
