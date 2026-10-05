from app.models import InfrastructureServer
from app.services.failure_domains import (
    failure_domain_overlap,
    failure_domain_sort_key,
)


def _server(*, provider, region, datacenter, physical_host, network_segment):
    return InfrastructureServer(
        name="test",
        hostname="test.example",
        provider=provider,
        region=region,
        datacenter=datacenter,
        physical_host=physical_host,
        network_segment=network_segment,
        roles_json='["application"]',
        status="active",
        created_by_user_id=None,
    )


def test_failure_domain_overlap_detects_critical_collisions():
    source = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-a",
    )
    target = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-b",
    )

    overlap = failure_domain_overlap(source, target)

    assert "physical_host" in overlap["shared"]
    assert overlap["highest_risk"] == "physical_host"
    assert overlap["penalty"] > 0


def test_failure_domain_sort_prefers_smaller_blast_radius_before_placement_score():
    source = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-a",
    )
    same_host = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-z",
    )
    other_region = _server(
        provider="p2",
        region="r2",
        datacenter="dc9",
        physical_host="host-z",
        network_segment="seg-z",
    )

    bad_overlap = failure_domain_overlap(source, same_host)
    good_overlap = failure_domain_overlap(source, other_region)

    bad_key = failure_domain_sort_key(
        bad_overlap,
        placement_score=1.0,
        name="fast-but-collocated",
        node_id="a",
    )
    good_key = failure_domain_sort_key(
        good_overlap,
        placement_score=50.0,
        name="safer",
        node_id="b",
    )

    assert good_key < bad_key


def test_failure_domain_overlap_penalties_are_progressive():
    source = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-a",
        network_segment="seg-a",
    )
    same_provider = _server(
        provider="p1",
        region="r9",
        datacenter="dc9",
        physical_host="host-z",
        network_segment="seg-z",
    )
    same_datacenter = _server(
        provider="p1",
        region="r1",
        datacenter="dc1",
        physical_host="host-z",
        network_segment="seg-z",
    )

    provider_overlap = failure_domain_overlap(source, same_provider)
    dc_overlap = failure_domain_overlap(source, same_datacenter)

    assert provider_overlap["penalty"] < dc_overlap["penalty"]
    assert provider_overlap["highest_risk"] == "provider"
    assert dc_overlap["highest_risk"] == "datacenter"


def test_smart_failover_prefers_safer_domain_over_better_placement_score(db, platform_owner, monkeypatch):
    from types import SimpleNamespace
    from app.models import InfrastructureNetworkObservation
    from app.services import smart_failover_ranking
    from datetime import datetime, timezone

    source = _server(provider="p1", region="r1", datacenter="dc1", physical_host="host-a", network_segment="seg-a")
    source.created_by_user_id = platform_owner.id
    risky = _server(provider="p1", region="r1", datacenter="dc1", physical_host="host-b", network_segment="seg-b")
    risky.hostname = "risky.example"
    risky.created_by_user_id = platform_owner.id
    safe = _server(provider="p2", region="r2", datacenter="dc2", physical_host="host-c", network_segment="seg-c")
    safe.hostname = "safe.example"
    safe.created_by_user_id = platform_owner.id
    db.add_all([source, risky, safe])
    db.flush()

    now = datetime.now(timezone.utc)
    db.add_all([
        InfrastructureNetworkObservation(
            source_server_id=source.id, target_server_id=risky.id, port=443,
            samples=3, successes=3, reachable=True, connect_loss_percent=0.0,
            latency_min_ms=1.0, latency_average_ms=1.0, latency_max_ms=1.0,
            jitter_average_ms=0.0, created_at=now,
        ),
        InfrastructureNetworkObservation(
            source_server_id=source.id, target_server_id=safe.id, port=443,
            samples=3, successes=3, reachable=True, connect_loss_percent=0.0,
            latency_min_ms=20.0, latency_average_ms=20.0, latency_max_ms=20.0,
            jitter_average_ms=0.0, created_at=now,
        ),
    ])
    db.flush()

    candidates = [
        ({"node": SimpleNamespace(id=risky.id), "name": "risky", "score": 1.0}, risky),
        ({"node": SimpleNamespace(id=safe.id), "name": "safe", "score": 50.0}, safe),
    ]
    ranked = smart_failover_ranking.rank_failover_candidates(
        db,
        source_server=source,
        candidates=candidates,
        now=now,
    )

    assert ranked[0]["target_server"].id == safe.id
    db.rollback()


def test_smart_failover_uses_network_path_when_domain_risk_matches(db, platform_owner):
    from types import SimpleNamespace
    from app.models import InfrastructureNetworkObservation
    from app.services import smart_failover_ranking
    from datetime import datetime, timezone

    source = _server(provider="p1", region="r1", datacenter="dc1", physical_host="host-a", network_segment="seg-a")
    source.hostname = "source-net.example"
    source.created_by_user_id = platform_owner.id
    fast = _server(provider="p2", region="r2", datacenter="dc2", physical_host="host-b", network_segment="seg-b")
    fast.hostname = "fast-net.example"
    fast.created_by_user_id = platform_owner.id
    slow = _server(provider="p3", region="r3", datacenter="dc3", physical_host="host-c", network_segment="seg-c")
    slow.hostname = "slow-net.example"
    slow.created_by_user_id = platform_owner.id
    db.add_all([source, fast, slow])
    db.flush()

    now = datetime.now(timezone.utc)
    db.add_all([
        InfrastructureNetworkObservation(
            source_server_id=source.id, target_server_id=fast.id, port=443,
            samples=5, successes=5, reachable=True, connect_loss_percent=0.0,
            latency_min_ms=5.0, latency_average_ms=5.0, latency_max_ms=5.0,
            jitter_average_ms=0.0, created_at=now,
        ),
        InfrastructureNetworkObservation(
            source_server_id=source.id, target_server_id=slow.id, port=443,
            samples=5, successes=5, reachable=True, connect_loss_percent=0.0,
            latency_min_ms=50.0, latency_average_ms=50.0, latency_max_ms=50.0,
            jitter_average_ms=0.0, created_at=now,
        ),
    ])
    db.flush()

    candidates = [
        ({"node": SimpleNamespace(id=slow.id), "name": "slow", "score": 1.0}, slow),
        ({"node": SimpleNamespace(id=fast.id), "name": "fast", "score": 20.0}, fast),
    ]
    ranked = smart_failover_ranking.rank_failover_candidates(
        db,
        source_server=source,
        candidates=candidates,
        now=now,
    )

    assert ranked[0]["target_server"].id == fast.id
    assert ranked[0]["route"]["reachable"] is True
    db.rollback()
