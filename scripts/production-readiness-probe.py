#!/usr/bin/env python3
"""Fail a release candidate when live readiness latency or reliability regresses."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.inf
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil((p / 100) * len(ordered)) - 1))
    return ordered[rank]


def request_once(url: str, timeout: float) -> tuple[bool, float, str]:
    started = time.perf_counter()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "ithute-production-readiness/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response.status != 200:
                return False, elapsed_ms, f"status={response.status}"
            payload = json.loads(body)
            if payload.get("status") not in {"ready", "ok"}:
                return False, elapsed_ms, f"unexpected-payload={payload!r}"
            return True, elapsed_ms, ""
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return False, (time.perf_counter() - started) * 1000, repr(exc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=1200)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--p95-ms", type=float, default=500.0)
    parser.add_argument("--p99-ms", type=float, default=1000.0)
    parser.add_argument("--max-error-rate", type=float, default=0.0)
    parser.add_argument("--warmup", type=int, default=40)
    args = parser.parse_args()

    for _ in range(args.warmup):
        ok, _, detail = request_once(args.url, args.timeout)
        if not ok:
            raise SystemExit(f"Warmup request failed: {detail}")

    latencies: list[float] = []
    errors: list[str] = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(request_once, args.url, args.timeout) for _ in range(args.requests)]
        for future in as_completed(futures):
            ok, elapsed_ms, detail = future.result()
            latencies.append(elapsed_ms)
            if not ok:
                errors.append(detail)

    duration = time.perf_counter() - started
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    error_rate = len(errors) / args.requests
    rps = args.requests / duration if duration else 0.0

    result = {
        "requests": args.requests,
        "concurrency": args.concurrency,
        "duration_seconds": round(duration, 3),
        "requests_per_second": round(rps, 2),
        "errors": len(errors),
        "error_rate": round(error_rate, 6),
        "latency_ms": {
            "mean": round(statistics.fmean(latencies), 2),
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "p99": round(p99, 2),
            "max": round(max(latencies), 2),
        },
        "thresholds": {
            "max_error_rate": args.max_error_rate,
            "p95_ms": args.p95_ms,
            "p99_ms": args.p99_ms,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))

    failed = False
    if error_rate > args.max_error_rate:
        print(f"FAIL: error rate {error_rate:.4%} exceeds {args.max_error_rate:.4%}")
        failed = True
    if p95 > args.p95_ms:
        print(f"FAIL: p95 {p95:.2f} ms exceeds {args.p95_ms:.2f} ms")
        failed = True
    if p99 > args.p99_ms:
        print(f"FAIL: p99 {p99:.2f} ms exceeds {args.p99_ms:.2f} ms")
        failed = True
    if errors:
        print("Sample errors:")
        for detail in errors[:10]:
            print(f"  - {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
