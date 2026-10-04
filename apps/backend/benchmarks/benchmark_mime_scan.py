from __future__ import annotations

import statistics
import time

from app.services import engine_runtime


def fixture() -> bytes:
    body = (b"Hello from Ithute mail acceleration.\r\n" * 4096)
    attachment = b"A" * (512 * 1024)
    return (
        b"From: sender@example.test\r\n"
        b"To: user@example.test\r\n"
        b"Subject: Engine benchmark\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/mixed; boundary=ithute-boundary\r\n"
        b"\r\n"
        b"--ithute-boundary\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        + body
        + b"\r\n--ithute-boundary\r\n"
        b"Content-Disposition: attachment; filename=\"payload.bin\"\r\n"
        b"Content-Type: application/octet-stream\r\n\r\n"
        + attachment
        + b"\r\n--ithute-boundary--\r\n"
    )


def measure(call, data: bytes, iterations: int = 100) -> float:
    samples = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        call(data)
        samples.append(time.perf_counter_ns() - started)
    return statistics.median(samples) / 1_000_000


def main() -> None:
    data = fixture()
    python_result = engine_runtime.python_mime_scan(data)
    native_result, engine = engine_runtime.mime_scan(data)
    if native_result != python_result:
        raise SystemExit(f"MIME scan mismatch: native={native_result!r} python={python_result!r}")

    python_ms = measure(engine_runtime.python_mime_scan, data)
    native_ms = measure(lambda raw: engine_runtime.mime_scan(raw)[0], data)
    ratio = python_ms / native_ms if native_ms else 0.0
    mib = len(data) / (1024 * 1024)
    print(
        f"mime-prescan benchmark engine={engine} payload_mib={mib:.2f} "
        f"python_median_ms={python_ms:.3f} native_median_ms={native_ms:.3f} "
        f"python_to_native_ratio={ratio:.2f}x"
    )


if __name__ == "__main__":
    main()
