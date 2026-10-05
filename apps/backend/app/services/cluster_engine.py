from __future__ import annotations

import ctypes
import math
import os
from collections import deque
from pathlib import Path


CLUSTER_LIBRARY = Path(
    os.getenv("ITHUTE_CPP_CLUSTER_LIBRARY", "/opt/ithute-engines/libithute_cpp_cluster.so")
)


class _ClusterSummary(ctypes.Structure):
    _fields_ = [
        ("nodes", ctypes.c_size_t),
        ("edges", ctypes.c_size_t),
        ("online_nodes", ctypes.c_size_t),
        ("healthy_nodes", ctypes.c_size_t),
        ("memory_total_bytes", ctypes.c_uint64),
        ("memory_used_bytes", ctypes.c_uint64),
        ("storage_total_bytes", ctypes.c_uint64),
        ("storage_used_bytes", ctypes.c_uint64),
    ]


_cluster: ctypes.CDLL | None = None
_cluster_load_attempted = False


def _load_cluster() -> ctypes.CDLL | None:
    global _cluster, _cluster_load_attempted
    if _cluster is not None:
        return _cluster
    if _cluster_load_attempted or not CLUSTER_LIBRARY.is_file():
        return None
    _cluster_load_attempted = True
    try:
        library = ctypes.CDLL(str(CLUSTER_LIBRARY))
        library.ithute_cluster_create.argtypes = []
        library.ithute_cluster_create.restype = ctypes.c_void_p
        library.ithute_cluster_destroy.argtypes = [ctypes.c_void_p]
        library.ithute_cluster_destroy.restype = None
        library.ithute_cluster_upsert_node.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_double,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.c_uint64,
        ]
        library.ithute_cluster_upsert_node.restype = ctypes.c_int
        library.ithute_cluster_upsert_edge.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint16,
        ]
        library.ithute_cluster_upsert_edge.restype = ctypes.c_int
        library.ithute_cluster_reachable.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        library.ithute_cluster_reachable.restype = ctypes.c_int
        library.ithute_cluster_summary_read.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_ClusterSummary),
        ]
        library.ithute_cluster_summary_read.restype = ctypes.c_int
        library.ithute_cluster_rank_candidates.argtypes = [
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_size_t,
        ]
        library.ithute_cluster_rank_candidates.restype = ctypes.c_int
    except (OSError, AttributeError):
        return None
    _cluster = library
    return library


def cluster_engine_status() -> dict:
    available = _load_cluster() is not None
    return {
        "available": available,
        "mode": "native",
        "library": str(CLUSTER_LIBRARY),
        "capabilities": ["cluster-graph", "graph-reachability", "cluster-summary", "placement-priority-queue"] if available else [],
        "fallback": "python",
    }


def _b(value: object) -> bytes:
    return str(value or "").encode("utf-8")


def _u64(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _f64(value: object) -> float:
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return max(0.0, min(result, 100.0))


def _status(value: object, online: bool) -> int:
    if online:
        return 1
    normalized = str(value or "").lower()
    if normalized == "maintenance":
        return 3
    if normalized in {"disabled", "offline"}:
        return 2
    return 0


_RELATIONS = {
    "communicates_with": 0,
    "hosts": 1,
    "depends_on": 2,
    "backs_up_to": 3,
    "replicates_to": 4,
}


def _python_summary(nodes: list[dict], edges: list[dict]) -> dict:
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "online_nodes": sum(1 for node in nodes if bool(node.get("online"))),
        "healthy_nodes": sum(1 for node in nodes if bool(node.get("healthy"))),
        "memory_total_bytes": sum(_u64(node.get("memory_total_bytes")) for node in nodes),
        "memory_used_bytes": sum(_u64(node.get("memory_used_bytes")) for node in nodes),
        "storage_total_bytes": sum(_u64(node.get("storage_total_bytes")) for node in nodes),
        "storage_used_bytes": sum(_u64(node.get("storage_used_bytes")) for node in nodes),
    }


def _python_reachable(nodes: list[dict], edges: list[dict], source: str, target: str) -> bool:
    ids = {str(node.get("id") or "") for node in nodes}
    if source not in ids or target not in ids:
        return False
    if source == target:
        return True
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        left = str(edge.get("source") or "")
        right = str(edge.get("target") or "")
        if left in ids and right in ids and left != right:
            adjacency.setdefault(left, []).append(right)
    pending = deque([source])
    seen = {source}
    while pending:
        current = pending.popleft()
        for neighbor in adjacency.get(current, []):
            if neighbor == target:
                return True
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return False


def _placement_sort_key(row: dict) -> tuple:
    try:
        score = float(row.get("score", 0.0))
    except (TypeError, ValueError, OverflowError):
        score = math.inf
    if not math.isfinite(score):
        score = math.inf
    name = str(row.get("name") or "").lower()
    node_id = str(row.get("node_id") or "")
    return (not bool(row.get("eligible")), score, name, node_id)


def _python_rank_candidates(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=_placement_sort_key)


def rank_placement_candidates(rows: list[dict]) -> list[dict]:
    """Rank placement candidates with the native priority queue and an exact Python fallback."""
    if len(rows) <= 1:
        return list(rows)

    library = _load_cluster()
    if library is None:
        return _python_rank_candidates(rows)

    count = len(rows)
    keys = (ctypes.c_char_p * count)()
    scores = (ctypes.c_double * count)()
    eligible = (ctypes.c_int * count)()
    order = (ctypes.c_size_t * count)()

    for index, row in enumerate(rows):
        _, score, name, node_id = _placement_sort_key(row)
        keys[index] = _b(f"{name}\x1f{node_id}")
        scores[index] = score
        eligible[index] = 1 if bool(row.get("eligible")) else 0

    try:
        code = library.ithute_cluster_rank_candidates(
            keys,
            scores,
            eligible,
            count,
            order,
            count,
        )
        if code != 0:
            raise RuntimeError("native placement ranking failed")
        ranked_indices = [int(order[index]) for index in range(count)]
        if sorted(ranked_indices) != list(range(count)):
            raise RuntimeError("native placement ranking returned invalid indices")
        return [rows[index] for index in ranked_indices]
    except (OSError, RuntimeError, ValueError, ctypes.ArgumentError):
        return _python_rank_candidates(rows)


def cluster_graph_analysis(
    nodes: list[dict],
    edges: list[dict],
    *,
    source: str | None = None,
    target: str | None = None,
) -> dict:
    """Analyze a sanitized topology snapshot with C++ and an exact Python fallback."""
    library = _load_cluster()
    if library is None:
        result = {"engine": "python-fallback", "summary": _python_summary(nodes, edges)}
        if source is not None and target is not None:
            result["reachable"] = _python_reachable(nodes, edges, source, target)
        return result

    handle = library.ithute_cluster_create()
    if not handle:
        return {"engine": "python-fallback", "summary": _python_summary(nodes, edges)}

    try:
        for node in nodes:
            code = library.ithute_cluster_upsert_node(
                handle,
                _b(node.get("id")),
                _b(node.get("name")),
                _b(node.get("private_ip")),
                _status(node.get("status"), bool(node.get("online"))),
                1 if bool(node.get("healthy")) else 0,
                _f64(node.get("cpu_used_percent")),
                _u64(node.get("memory_total_bytes")),
                _u64(node.get("memory_used_bytes")),
                _u64(node.get("storage_total_bytes")),
                _u64(node.get("storage_used_bytes")),
            )
            if code != 0:
                raise RuntimeError("native cluster node ingestion failed")

        for edge in edges:
            protocol = str(edge.get("protocol") or "").lower()
            port = max(0, min(_u64(edge.get("port")), 65535))
            code = library.ithute_cluster_upsert_edge(
                handle,
                _b(edge.get("source")),
                _b(edge.get("target")),
                _RELATIONS.get(str(edge.get("relation") or "").lower(), 0),
                _b(edge.get("service")),
                protocol.encode("utf-8"),
                port,
            )
            if code != 0:
                continue

        output = _ClusterSummary()
        if library.ithute_cluster_summary_read(handle, ctypes.byref(output)) != 0:
            raise RuntimeError("native cluster summary failed")
        result = {
            "engine": "cpp",
            "summary": {
                "nodes": output.nodes,
                "edges": output.edges,
                "online_nodes": output.online_nodes,
                "healthy_nodes": output.healthy_nodes,
                "memory_total_bytes": output.memory_total_bytes,
                "memory_used_bytes": output.memory_used_bytes,
                "storage_total_bytes": output.storage_total_bytes,
                "storage_used_bytes": output.storage_used_bytes,
            },
        }
        if source is not None and target is not None:
            reachable = library.ithute_cluster_reachable(handle, _b(source), _b(target))
            result["reachable"] = reachable == 1
        return result
    except (OSError, RuntimeError, ValueError, ctypes.ArgumentError):
        result = {"engine": "python-fallback", "summary": _python_summary(nodes, edges)}
        if source is not None and target is not None:
            result["reachable"] = _python_reachable(nodes, edges, source, target)
        return result
    finally:
        library.ithute_cluster_destroy(handle)
