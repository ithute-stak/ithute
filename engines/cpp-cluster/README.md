# Ithute C++ Cluster Graph Engine

This module is the algorithmic topology core for Ithute's distributed infrastructure.

Phase 1 deliberately focuses on a small, deterministic in-memory graph:

- `std::unordered_map` node registry for fast node lookup;
- adjacency lists for sparse infrastructure relationships;
- node and edge upsert/remove;
- neighbor discovery;
- breadth-first reachability;
- aggregate cluster resource summary.

The graph contains sanitized operational state only. Secrets, private keys, tokens,
environment variables, customer credentials and arbitrary shell data do not belong
in this engine.

## Relationship model

Edges can represent:

- `CommunicatesWith`
- `Hosts`
- `DependsOn`
- `BacksUpTo`
- `ReplicatesTo`

The initial implementation is intentionally independent of the Python control plane.
Python remains authoritative for tenancy, authorization, persistence and orchestration.
The C++ engine is an algorithm/data-structure component, not a source of truth.

## Build and test

```bash
cmake -S engines/cpp-cluster -B /tmp/ithute-cpp-cluster -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/ithute-cpp-cluster --parallel 2
ctest --test-dir /tmp/ithute-cpp-cluster --output-on-failure
```

## Next phases

1. Snapshot adapter from sanitized Ithute cluster-state data.
2. Resource reservation/capacity model.
3. Priority-queue placement candidates.
4. Dependency topological sorting and cycle detection.
5. Weighted path and failure-domain algorithms.
