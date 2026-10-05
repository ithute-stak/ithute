from __future__ import annotations

import statistics
import time

from app.services import engine_runtime


PAYLOAD = (bytes(range(256)) * 16384) + (b"Ithute-C++-blob-profile\x00\x01" * 4096)


def measure(call, iterations: int = 12) -> float:
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        call(PAYLOAD)
        samples.append(time.perf_counter_ns() - started)
    return statistics.median(samples) / 1_000_000


def main() -> None:
    python_profile = engine_runtime.python_blob_profile(PAYLOAD)
    native_profile, engine = engine_runtime.blob_profile(PAYLOAD)
    if native_profile != python_profile:
        raise SystemExit(f"blob profile mismatch: native={native_profile!r} python={python_profile!r}")
    if engine != "cpp":
        raise SystemExit(f"expected C++ engine, got {engine}")

    python_ms = measure(engine_runtime.python_blob_profile)
    cpp_ms = measure(lambda data: engine_runtime.blob_profile(data)[0])
    speedup = python_ms / cpp_ms if cpp_ms else 0.0
    print(
        f"blob profile benchmark payload_mib={len(PAYLOAD)/(1024*1024):.2f} "
        f"python_median_ms={python_ms:.3f} cpp_median_ms={cpp_ms:.3f} "
        f"speedup={speedup:.2f}x"
    )
    if speedup < 2.0:
        raise SystemExit(f"C++ blob profile speedup {speedup:.2f}x is below required 2.0x")


if __name__ == "__main__":
    main()
