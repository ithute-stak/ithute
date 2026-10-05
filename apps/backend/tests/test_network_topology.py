from uuid import uuid4

from app.services.network_topology import _normalize_observation


def test_network_topology_normalizes_valid_measurement():
    source = uuid4()
    target = uuid4()
    item = {
        "id": str(target),
        "port": 443,
        "attempts": 3,
        "successes": 3,
        "reachable": True,
        "connect_loss_percent": 0.0,
        "latency_min_ms": 2.0,
        "latency_average_ms": 3.0,
        "latency_max_ms": 4.0,
        "jitter_average_ms": 0.5,
    }

    normalized = _normalize_observation(source, item, default_samples=3)

    assert normalized is not None
    assert normalized["target_server_id"] == target
    assert normalized["samples"] == 3
    assert normalized["successes"] == 3
    assert normalized["reachable"] is True


def test_network_topology_rejects_self_edge_and_inconsistent_reachability():
    source = uuid4()
    self_edge = {
        "id": str(source),
        "port": 443,
        "attempts": 3,
        "successes": 3,
        "reachable": True,
        "connect_loss_percent": 0.0,
        "latency_min_ms": 1.0,
        "latency_average_ms": 1.0,
        "latency_max_ms": 1.0,
        "jitter_average_ms": 0.0,
    }
    assert _normalize_observation(source, self_edge, default_samples=3) is None

    target = uuid4()
    inconsistent = {
        **self_edge,
        "id": str(target),
        "successes": 0,
        "reachable": True,
        "connect_loss_percent": 100.0,
    }
    assert _normalize_observation(source, inconsistent, default_samples=3) is None


def test_network_topology_rejects_invalid_latency_order():
    source = uuid4()
    item = {
        "id": str(uuid4()),
        "port": 5432,
        "attempts": 3,
        "successes": 2,
        "reachable": True,
        "connect_loss_percent": 33.333,
        "latency_min_ms": 8.0,
        "latency_average_ms": 4.0,
        "latency_max_ms": 6.0,
        "jitter_average_ms": 1.0,
    }

    assert _normalize_observation(source, item, default_samples=3) is None
