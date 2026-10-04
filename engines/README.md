# Ithute specialist engines

Ithute uses a strict multi-engine model:

- **Python/FastAPI** — control plane, authorization, tenancy, billing, APIs,
  database orchestration and business rules.
- **Rust core** — memory-safe native acceleration for bounded CPU-heavy parsing,
  MIME pre-scans, attachment/content SHA-256 hashing and data transformations.
- **Go worker** — concurrent/network-oriented workers and service probes.
- **C++ native** — narrow benchmark-proven hot paths only.
- **Java worker** — enterprise XML/report/integration processing with hardened parsers.

No specialist engine is allowed to independently authorize a tenant action or
reimplement billing/permission rules. Python decides **what** may happen;
specialist engines execute bounded **how** work.

The initial native operations are intentionally small. They establish build,
ABI, health and observability boundaries before production logic is migrated.


## Routing model

Python owns the routing policy. The control plane currently prefers:

- `mail.byte_stats`, `mail.mime_scan`, `mail.sha256` -> Rust
- `network.concurrent` -> Go
- `enterprise.xml` -> Java
- `native.fingerprint` -> C++

Every routed operation keeps a Python fallback so a specialist engine failure
does not take down mailbox or control-plane requests.
