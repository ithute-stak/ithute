from __future__ import annotations

from app.models import InfrastructureServer
from app.services.failure_domains import failure_domain_overlap


CRITICAL_ANTI_AFFINITY_LEVELS = {"physical_host", "network_segment"}
PREFERRED_DIVERSITY_LEVELS = ("datacenter", "region", "provider")


def anti_affinity_evaluation(
    source: InfrastructureServer | None,
    target: InfrastructureServer | None,
    *,
    require_datacenter_diversity: bool = False,
    require_region_diversity: bool = False,
    require_provider_diversity: bool = False,
) -> dict:
    """Evaluate whether target is a safe replica/backup destination for source."""
    overlap = failure_domain_overlap(source, target)
    shared = set(overlap["shared"])
    violations: list[str] = []

    for level in sorted(CRITICAL_ANTI_AFFINITY_LEVELS):
        if level in shared:
            violations.append(level)

    if require_datacenter_diversity and "datacenter" in shared:
        violations.append("datacenter")
    if require_region_diversity and "region" in shared:
        violations.append("region")
    if require_provider_diversity and "provider" in shared:
        violations.append("provider")

    diversity = {
        level: level not in shared
        for level in ("physical_host", "network_segment", "datacenter", "region", "provider")
    }

    return {
        "eligible": not violations,
        "violations": violations,
        "shared": overlap["shared"],
        "diversity": diversity,
        "penalty": overlap["penalty"],
        "highest_risk": overlap["highest_risk"],
    }


def anti_affinity_sort_key(evaluation: dict, *, score: float, name: str, server_id: str) -> tuple:
    diversity = evaluation.get("diversity") or {}
    preferred_diversity = sum(1 for level in PREFERRED_DIVERSITY_LEVELS if diversity.get(level))
    return (
        not bool(evaluation.get("eligible")),
        -preferred_diversity,
        float(evaluation.get("penalty") or 0.0),
        float(score),
        str(name or "").lower(),
        str(server_id or ""),
    )
