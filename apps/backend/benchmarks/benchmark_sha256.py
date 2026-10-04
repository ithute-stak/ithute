from __future__ import annotations

import statistics
import time

from app.services import engine_runtime


def fixture() -> bytes:
    return (b"Ithute attachment payload\n" * 32768) + (b"x" * (1024 * 1024))


def measure(call, data: bytes, iterations: int = 50) -> float:
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        call(data)
        samples.append(time.perf_counter_ns() - started)
    return statistics.median(samples) / 1_000_000


def main() -> None:
    data = fixture()
    python_digest = engine_runtime.python_sha256(data)
    native_digest, engine = engine_runtime.sha256_digest(data)
    if native_digest != python_digest:
        raise SystemExit(
            f"SHA-256 mismatch: native={native_digest!r} python={python_digest!r}"
        )

    python_ms = measure(engine_runtime.python_sha256, data)
    native_ms = measure(lambda raw: engine_runtime.sha256_digest(raw)[0], data)
    ratio = python_ms / native_ms if native_ms else 0.0
    mib = len(data) / (1024 * 1024)
    print(
        f"sha256 benchmark engine={engine} payload_mib={mib:.2f} "
        f"python_median_ms={python_ms:.3f} native_median_ms={native_ms:.3f} "
        f"python_to_native_ratio={ratio:.2f}x"
    )


if __name__ == "__main__":
    main()
