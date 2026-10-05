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
