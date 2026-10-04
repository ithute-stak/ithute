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
