# Ithute specialist engines

Ithute uses a strict multi-engine model:

- **Python/FastAPI** — control plane, authorization, tenancy, billing, APIs,
  database orchestration and business rules.
- **Rust core** — memory-safe native acceleration for bounded CPU-heavy parsing
  and data transformations.
- **Go worker** — concurrent/network-oriented workers and service probes.
- **C++ native** — narrow benchmark-proven hot paths only.
- **Java worker** — enterprise XML/report/integration processing with hardened parsers.

No specialist engine is allowed to independently authorize a tenant action or
reimplement billing/permission rules. Python decides **what** may happen;
specialist engines execute bounded **how** work.

The initial native operations are intentionally small. They establish build,
ABI, health and observability boundaries before production logic is migrated.
