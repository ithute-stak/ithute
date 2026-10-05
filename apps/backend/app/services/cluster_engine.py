from __future__ import annotations

import ctypes
import heapq
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
        library.ithute_cluster_dependency_order.argtypes = [
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_size_t,
        ]
        library.ithute_cluster_dependency_order.restype = ctypes.c_int
        library.ithute_cluster_shortest_path.argtypes = [
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_double),
        ]
        library.ithute_cluster_shortest_path.restype = ctypes.c_int
        library.ithute_cluster_network_partitions.argtypes = [
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        library.ithute_cluster_network_partitions.restype = ctypes.c_int
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
        "capabilities": ["cluster-graph", "graph-reachability", "cluster-summary", "placement-priority-queue", "dependency-dag", "topological-order", "weighted-shortest-path", "network-partitions"] if available else [],
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


def _dependency_ids(nodes: list[dict]) -> list[str]:
    return [str(node.get("id") or "") for node in nodes]


def _dependency_edges(edges: list[dict]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for edge in edges:
        if str(edge.get("relation") or "").lower() != "depends_on":
            continue
        result.append((str(edge.get("source") or ""), str(edge.get("target") or "")))
    return result


def _python_dependency_order(nodes: list[dict], edges: list[dict]) -> dict:
    ids = _dependency_ids(nodes)
    if not ids:
        return {"engine": "python-fallback", "acyclic": True, "order": []}
    if any(not node_id for node_id in ids) or len(set(ids)) != len(ids):
        return {"engine": "python-fallback", "acyclic": False, "order": [], "error": "invalid node ids"}

    known = set(ids)
    remaining = {node_id: 0 for node_id in ids}
    dependents = {node_id: set() for node_id in ids}
    for dependent, dependency in _dependency_edges(edges):
        if dependent not in known or dependency not in known or dependent == dependency:
            return {"engine": "python-fallback", "acyclic": False, "order": [], "error": "invalid dependency edge"}
        if dependent in dependents[dependency]:
            continue
        dependents[dependency].add(dependent)
        remaining[dependent] += 1

    ready = [node_id for node_id, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        current = heapq.heappop(ready)
        order.append(current)
        for dependent in sorted(dependents[current]):
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                heapq.heappush(ready, dependent)

    return {
        "engine": "python-fallback",
        "acyclic": len(order) == len(ids),
        "order": order if len(order) == len(ids) else [],
    }


def dependency_order(nodes: list[dict], edges: list[dict]) -> dict:
    """Return dependency-first deployment order; reject cyclic dependency graphs."""
    ids = _dependency_ids(nodes)
    if not ids:
        return {"engine": "cpp" if _load_cluster() is not None else "python-fallback", "acyclic": True, "order": []}

    fallback = _python_dependency_order(nodes, edges)
    if not fallback["acyclic"] and fallback.get("error"):
        return fallback

    library = _load_cluster()
    if library is None:
        return fallback

    dependency_pairs = _dependency_edges(edges)
    count = len(ids)
    edge_count = len(dependency_pairs)
    node_ids = (ctypes.c_char_p * count)(*[_b(node_id) for node_id in ids])
    dependents = (ctypes.c_char_p * edge_count)(*[_b(pair[0]) for pair in dependency_pairs]) if edge_count else None
    dependencies = (ctypes.c_char_p * edge_count)(*[_b(pair[1]) for pair in dependency_pairs]) if edge_count else None
    order = (ctypes.c_size_t * count)()

    try:
        code = library.ithute_cluster_dependency_order(
            node_ids,
            count,
            dependents,
            dependencies,
            edge_count,
            order,
            count,
        )
        if code == 3:
            return {"engine": "cpp", "acyclic": False, "order": []}
        if code != 0:
            raise RuntimeError("native dependency ordering failed")
        ranked_indices = [int(order[index]) for index in range(count)]
        if sorted(ranked_indices) != list(range(count)):
            raise RuntimeError("native dependency ordering returned invalid indices")
        return {"engine": "cpp", "acyclic": True, "order": [ids[index] for index in ranked_indices]}
    except (OSError, RuntimeError, ValueError, ctypes.ArgumentError):
        return fallback


def _python_shortest_weighted_path(node_ids: list[str], edges: list[dict], source: str, target: str) -> dict:
    if source not in node_ids or target not in node_ids or len(set(node_ids)) != len(node_ids):
        return {"engine": "python-fallback", "reachable": False, "path": [], "total_weight": None}
    index = {node_id: i for i, node_id in enumerate(node_ids)}
    adjacency: dict[str, list[tuple[str, float]]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        left = str(edge.get("source") or "")
        right = str(edge.get("target") or "")
        try:
            weight = float(edge.get("weight"))
        except (TypeError, ValueError, OverflowError):
            continue
        if left not in index or right not in index or not math.isfinite(weight) or weight < 0:
            continue
        adjacency[left].append((right, weight))

    distances = {node_id: math.inf for node_id in node_ids}
    previous: dict[str, str] = {}
    distances[source] = 0.0
    pending: list[tuple[float, str]] = [(0.0, source)]
    while pending:
        distance, current = heapq.heappop(pending)
        if distance != distances[current]:
            continue
        if current == target:
            break
        for neighbor, weight in sorted(adjacency[current], key=lambda item: item[0]):
            candidate = distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = current
                heapq.heappush(pending, (candidate, neighbor))

    if not math.isfinite(distances[target]):
        return {"engine": "python-fallback", "reachable": False, "path": [], "total_weight": None}

    path = [target]
    while path[-1] != source:
        parent = previous.get(path[-1])
        if parent is None:
            return {"engine": "python-fallback", "reachable": False, "path": [], "total_weight": None}
        path.append(parent)
    path.reverse()
    return {"engine": "python-fallback", "reachable": True, "path": path, "total_weight": distances[target]}


def shortest_weighted_path(node_ids: list[str], edges: list[dict], *, source: str, target: str) -> dict:
    fallback = _python_shortest_weighted_path(node_ids, edges, source, target)
    if not node_ids:
        return fallback
    library = _load_cluster()
    if library is None:
        return fallback
    if source not in node_ids or target not in node_ids or len(set(node_ids)) != len(node_ids):
        return fallback

    index = {node_id: i for i, node_id in enumerate(node_ids)}
    valid_edges: list[tuple[int, int, float]] = []
    for edge in edges:
        left = str(edge.get("source") or "")
        right = str(edge.get("target") or "")
        try:
            weight = float(edge.get("weight"))
        except (TypeError, ValueError, OverflowError):
            continue
        if left not in index or right not in index or not math.isfinite(weight) or weight < 0:
            continue
        valid_edges.append((index[left], index[right], weight))

    count = len(valid_edges)
    sources = (ctypes.c_size_t * count)(*[row[0] for row in valid_edges]) if count else None
    targets = (ctypes.c_size_t * count)(*[row[1] for row in valid_edges]) if count else None
    weights = (ctypes.c_double * count)(*[row[2] for row in valid_edges]) if count else None
    out = (ctypes.c_size_t * len(node_ids))()
    out_count = ctypes.c_size_t()
    out_weight = ctypes.c_double()

    try:
        code = library.ithute_cluster_shortest_path(
            len(node_ids), sources, targets, weights, count,
            index[source], index[target], out, len(node_ids),
            ctypes.byref(out_count), ctypes.byref(out_weight),
        )
        if code == 3:
            return {"engine": "cpp", "reachable": False, "path": [], "total_weight": None}
        if code != 0:
            raise RuntimeError("native weighted shortest path failed")
        path_indices = [int(out[i]) for i in range(int(out_count.value))]
        if any(i < 0 or i >= len(node_ids) for i in path_indices):
            raise RuntimeError("native weighted shortest path returned invalid indices")
        return {
            "engine": "cpp",
            "reachable": True,
            "path": [node_ids[i] for i in path_indices],
            "total_weight": float(out_weight.value),
        }
    except (OSError, RuntimeError, ValueError, ctypes.ArgumentError):
        return fallback


def _python_network_partitions(node_ids: list[str], links: list[tuple[str, str]]) -> dict:
    if not node_ids or len(set(node_ids)) != len(node_ids):
        return {"engine": "python-fallback", "components": [], "component_count": 0}
    parent = {node_id: node_id for node_id in node_ids}

    def find(node_id: str) -> str:
        while parent[node_id] != node_id:
            parent[node_id] = parent[parent[node_id]]
            node_id = parent[node_id]
        return node_id

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            if root_left < root_right:
                parent[root_right] = root_left
            else:
                parent[root_left] = root_right

    known = set(node_ids)
    for left, right in links:
        if left in known and right in known:
            union(left, right)

    grouped: dict[str, list[str]] = {}
    for node_id in sorted(node_ids):
        grouped.setdefault(find(node_id), []).append(node_id)
    components = sorted(grouped.values(), key=lambda group: group[0] if group else "")
    return {"engine": "python-fallback", "components": components, "component_count": len(components)}


def network_partitions(node_ids: list[str], links: list[tuple[str, str]]) -> dict:
    fallback = _python_network_partitions(node_ids, links)
    if not node_ids:
        return fallback
    library = _load_cluster()
    if library is None or len(set(node_ids)) != len(node_ids):
        return fallback

    index = {node_id: i for i, node_id in enumerate(node_ids)}
    valid = [(index[left], index[right]) for left, right in links if left in index and right in index]
    count = len(valid)
    sources = (ctypes.c_size_t * count)(*[row[0] for row in valid]) if count else None
    targets = (ctypes.c_size_t * count)(*[row[1] for row in valid]) if count else None
    component_ids = (ctypes.c_size_t * len(node_ids))()
    component_count = ctypes.c_size_t()

    try:
        code = library.ithute_cluster_network_partitions(
            len(node_ids), sources, targets, count,
            component_ids, len(node_ids), ctypes.byref(component_count),
        )
        if code != 0:
            raise RuntimeError("native network partition detection failed")
        grouped: dict[int, list[str]] = {}
        for i, node_id in enumerate(node_ids):
            grouped.setdefault(int(component_ids[i]), []).append(node_id)
        components = [sorted(group) for _, group in sorted(grouped.items())]
        return {"engine": "cpp", "components": components, "component_count": int(component_count.value)}
    except (OSError, RuntimeError, ValueError, ctypes.ArgumentError):
        return fallback


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
