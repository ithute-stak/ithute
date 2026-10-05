from datetime import datetime, timedelta, timezone

from app.services import network_route_policy


def _obs(source, target, *, latency, loss=0.0, jitter=0.0, samples=5, successes=5, age_seconds=0, congestion=0.0):
    now = datetime(2026, 10, 5, 18, 45, tzinfo=timezone.utc)
    return {
        "source_server_id": source,
        "target_server_id": target,
        "reachable": successes > 0,
        "latency_average_ms": latency,
        "jitter_average_ms": jitter,
        "connect_loss_percent": loss,
        "samples": samples,
        "successes": successes,
        "congestion_percent": congestion,
        "created_at": now - timedelta(seconds=age_seconds),
    }


def test_route_edge_weight_is_explainable():
    now = datetime(2026, 10, 5, 18, 45, tzinfo=timezone.utc)
    weighted = network_route_policy.route_edge_weight(
        _obs("a", "b", latency=10.0, loss=2.0, jitter=4.0, samples=5, successes=4, age_seconds=60, congestion=20.0),
        now=now,
    )

    assert weighted is not None
    assert weighted["components"] == {
        "latency": 10.0,
        "connect_loss": 10.0,
        "jitter": 6.0,
        "staleness": 2.0,
        "reliability": 10.0,
        "congestion": 20.0,
    }
    assert weighted["weight"] == 58.0


def test_route_edge_weight_rejects_unreachable_or_stale_observation():
    now = datetime(2026, 10, 5, 18, 45, tzinfo=timezone.utc)
    unreachable = _obs("a", "b", latency=0.0, samples=3, successes=0)
    stale = _obs("a", "b", latency=3.0, age_seconds=network_route_policy.MAX_ROUTE_OBSERVATION_AGE_SECONDS + 1)

    assert network_route_policy.route_edge_weight(unreachable, now=now) is None
    assert network_route_policy.route_edge_weight(stale, now=now) is None


def test_build_weighted_edges_uses_latest_observation_only():
    now = datetime(2026, 10, 5, 18, 45, tzinfo=timezone.utc)
    older = _obs("a", "b", latency=50.0, age_seconds=120)
    newer = _obs("a", "b", latency=5.0, age_seconds=10)

    edges = network_route_policy.build_weighted_network_edges([older, newer], now=now)

    assert len(edges) == 1
    assert edges[0]["source"] == "a"
    assert edges[0]["target"] == "b"
    assert edges[0]["components"]["latency"] == 5.0


def test_best_network_route_prefers_healthier_multihop_path(monkeypatch):
    now = datetime(2026, 10, 5, 18, 45, tzinfo=timezone.utc)
    monkeypatch.setattr(network_route_policy, "shortest_weighted_path", lambda node_ids, edges, source, target: {
        "engine": "test",
        "reachable": True,
        "path": ["a", "b", "d"],
        "total_weight": next(edge["weight"] for edge in edges if edge["source"] == "a" and edge["target"] == "b")
        + next(edge["weight"] for edge in edges if edge["source"] == "b" and edge["target"] == "d"),
    })

    observations = [
        _obs("a", "b", latency=5.0),
        _obs("b", "d", latency=5.0),
        _obs("a", "c", latency=2.0, loss=20.0, jitter=10.0),
        _obs("c", "d", latency=2.0, loss=20.0, jitter=10.0),
    ]

    result = network_route_policy.best_network_route(
        ["a", "b", "c", "d"],
        observations,
        source="a",
        target="d",
        now=now,
    )

    assert result["reachable"] is True
    assert result["path"] == ["a", "b", "d"]
    healthy_weight = next(edge["weight"] for edge in result["edges"] if edge["source"] == "a" and edge["target"] == "b")
    lossy_weight = next(edge["weight"] for edge in result["edges"] if edge["source"] == "a" and edge["target"] == "c")
    assert healthy_weight < lossy_weight
