# Ithute multi-engine architecture

## Authority

Python/FastAPI remains the backend brain. Next.js/React remains the frontend UI
brain. Specialist engines do not own tenant authorization, billing, permission
checks, product rules or database policy.

## Backend engines

| Engine | Responsibility | Initial integration |
| --- | --- | --- |
| Python | APIs, auth, tenancy, billing, orchestration, PostgreSQL/Redis | authoritative |
| Rust | memory-safe CPU-heavy parsing/transformation | native shared library with Python fallback |
| Go | concurrent/network workers | isolated internal worker image |
| C++ | benchmark-proven hot paths only | native shared library with Python fallback |
| Java | enterprise XML/report/integration processing | isolated internal worker with Python fallback |

The API exposes platform-owner engine status at `GET /api/v1/platform/engines`.
The native libraries are loaded from `/opt/ithute-engines` in the immutable API
image. A native load or call failure never transfers business authority; Python
uses its bounded fallback.

## Frontend engine boundary

Next.js continues to render and own UI state. Browser-heavy work is dispatched
through `lib/browser-engine.ts` to `workers/ithute-compute.worker.ts`. If the
worker is unavailable or fails, the caller gets the TypeScript fallback.

Rust/WASM can later replace worker internals operation-by-operation without
changing page-level APIs.

## Non-negotiable rules

1. No duplicated business authorization between languages.
2. No engine receives unrestricted database credentials.
3. Every cross-engine operation is bounded and versioned.
4. Native/WASM acceleration must have a correctness test against the reference implementation.
5. C++ enters a production hot path only after profiling/benchmark evidence.
6. Go workers execute approved jobs; they do not decide whether a tenant is entitled to the job.
7. Engine failure must degrade a bounded capability, not take down authentication or the control plane.


## First production acceleration: iMail MIME pre-scan

The first real workload moved behind the Rust boundary is the raw RFC822/MIME
pre-scan used by hosted webmail message parsing.

Rust now computes bounded structural facts such as message/header/body byte
counts, line-ending counts, non-ASCII/NUL bytes, MIME boundary markers and a
conservative attachment signal. Python's `email` parser remains authoritative
for headers, body decoding and attachment metadata.

When the pre-scan proves that no attachment signal exists, Ithute skips a
redundant Python MIME-tree attachment walk. If Rust is unavailable or returns an
error, the exact same pre-scan contract is implemented in Python and parsing
continues normally.

Prometheus exposes engine/attachment-walk counters and message-size histograms.
CI also runs a parity benchmark but deliberately does not enforce a fixed speed
ratio because runner performance varies.


## Java enterprise engine

Java is introduced for bounded enterprise integration/report workloads where its
mature XML and protocol ecosystem is useful. The first production capability is
DMARC aggregate XML parsing. The Java worker has no database credentials and no
tenant/business authority. Python verifies the tenant/domain, bounds and
decompresses uploads, invokes Java, validates the returned domain/report data,
and persists the resulting summary.

The parser disables DTDs, external entities, external schemas and XInclude to
avoid XXE-style behavior. If Java is unavailable, Ithute falls back to the
bounded Python reference parser.
