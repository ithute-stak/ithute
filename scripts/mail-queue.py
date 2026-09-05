#!/usr/bin/env python3
"""Structured Postfix queue inspection for the Phase 8 operations plane.

This helper intentionally supports read-only queue inspection by default. Queue
mutations remain explicit operator actions executed inside the Postfix container.
"""
import json
import subprocess
import sys


def queue_json() -> list[dict]:
    proc = subprocess.run(["postqueue", "-j"], check=True, capture_output=True, text=True)
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main() -> None:
    rows = queue_json()
    if "--summary" in sys.argv:
        deferred = sum(1 for row in rows if row.get("delay_reason"))
        print(json.dumps({"queued": len(rows), "deferred": deferred}, sort_keys=True))
        return
    print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
