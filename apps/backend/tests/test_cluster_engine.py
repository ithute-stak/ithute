from app.services import cluster_engine


def test_cluster_graph_python_fallback_summary_and_reachability(monkeypatch):
    monkeypatch.setattr(cluster_engine, "_load_cluster", lambda: None)
    nodes = [
        {
            "id": "a",
            "name": "A",
            "online": True,
            "healthy": True,
            "memory_total_bytes": 8,
            "memory_used_bytes": 3,
            "storage_total_bytes": 100,
            "storage_used_bytes": 40,
        },
        {
            "id": "b",
            "name": "B",
            "online": True,
            "healthy": True,
            "memory_total_bytes": 16,
            "memory_used_bytes": 6,
            "storage_total_bytes": 200,
            "storage_used_bytes": 80,
        },
        {
            "id": "c",
            "name": "C",
            "online": False,
            "healthy": False,
            "memory_total_bytes": 32,
            "memory_used_bytes": 4,
            "storage_total_bytes": 500,
            "storage_used_bytes": 100,
        },
    ]
    edges = [
        {"source": "a", "target": "b", "relation": "depends_on"},
        {"source": "b", "target": "c", "relation": "backs_up_to"},
    ]

    result = cluster_engine.cluster_graph_analysis(nodes, edges, source="a", target="c")

    assert result["engine"] == "python-fallback"
    assert result["reachable"] is True
    assert result["summary"] == {
        "nodes": 3,
        "edges": 2,
        "online_nodes": 2,
        "healthy_nodes": 2,
        "memory_total_bytes": 56,
        "memory_used_bytes": 13,
        "storage_total_bytes": 800,
        "storage_used_bytes": 220,
    }


def test_cluster_graph_rejects_unknown_path_in_fallback(monkeypatch):
    monkeypatch.setattr(cluster_engine, "_load_cluster", lambda: None)
    result = cluster_engine.cluster_graph_analysis(
        [{"id": "a", "online": True, "healthy": True}],
        [],
        source="a",
        target="missing",
    )
    assert result["reachable"] is False



def test_placement_ranking_fallback_matches_scheduler_contract(monkeypatch):
    monkeypatch.setattr(cluster_engine, "_load_cluster", lambda: None)
    rows = [
        {"node_id": "c", "name": "Charlie", "eligible": True, "score": 20.0},
        {"node_id": "b", "name": "Bravo", "eligible": True, "score": 10.0},
        {"node_id": "a", "name": "Alpha", "eligible": True, "score": 10.0},
        {"node_id": "z", "name": "Zulu", "eligible": False, "score": 1.0},
    ]

    ranked = cluster_engine.rank_placement_candidates(rows)

    assert [row["node_id"] for row in ranked] == ["a", "b", "c", "z"]



def test_dependency_order_fallback_is_dependency_first(monkeypatch):
    monkeypatch.setattr(cluster_engine, "_load_cluster", lambda: None)
    nodes = [{"id": "frontend"}, {"id": "backend"}, {"id": "postgres"}]
    edges = [
        {"source": "frontend", "target": "backend", "relation": "depends_on"},
        {"source": "backend", "target": "postgres", "relation": "depends_on"},
    ]

    result = cluster_engine.dependency_order(nodes, edges)

    assert result == {
        "engine": "python-fallback",
        "acyclic": True,
        "order": ["postgres", "backend", "frontend"],
    }


def test_dependency_order_fallback_rejects_cycle(monkeypatch):
    monkeypatch.setattr(cluster_engine, "_load_cluster", lambda: None)
    nodes = [{"id": "frontend"}, {"id": "backend"}, {"id": "postgres"}]
    edges = [
        {"source": "frontend", "target": "backend", "relation": "depends_on"},
        {"source": "backend", "target": "postgres", "relation": "depends_on"},
        {"source": "postgres", "target": "frontend", "relation": "depends_on"},
    ]

    result = cluster_engine.dependency_order(nodes, edges)

    assert result["acyclic"] is False
    assert result["order"] == []



def test_weighted_shortest_path_fallback(monkeypatch):
    monkeypatch.setattr(cluster_engine, "_load_cluster", lambda: None)
    result = cluster_engine.shortest_weighted_path(
        ["a", "b", "c", "d"],
        [
            {"source": "a", "target": "b", "weight": 2.0},
            {"source": "a", "target": "c", "weight": 10.0},
            {"source": "b", "target": "d", "weight": 2.0},
            {"source": "c", "target": "d", "weight": 1.0},
        ],
        source="a",
        target="d",
    )
    assert result == {
        "engine": "python-fallback",
        "reachable": True,
        "path": ["a", "b", "d"],
        "total_weight": 4.0,
    }



def test_network_partitions_fallback(monkeypatch):
    monkeypatch.setattr(cluster_engine, "_load_cluster", lambda: None)
    result = cluster_engine.network_partitions(
        ["a", "b", "c", "d", "e"],
        [("a", "b"), ("b", "c"), ("d", "e")],
    )
    assert result["engine"] == "python-fallback"
    assert result["component_count"] == 2
    assert result["components"] == [["a", "b", "c"], ["d", "e"]]
