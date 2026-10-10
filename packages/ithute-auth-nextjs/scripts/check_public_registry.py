#!/usr/bin/env python3
"""Read-only npm registry check. Registry 404 never establishes package ownership."""
import argparse
import json
import sys
import urllib.error
import urllib.request

REGISTRY = "https://registry.npmjs.org/ithute-auth"
USER_AGENT = "ithute-auth-release-readiness/1.0"


def classify(status, body):
    if status == 404:
        return 2, "Package record not found (404). Name ownership and permission to publish remain unverified."
    if status != 200:
        return 1, f"npm registry returned HTTP {status}; release is blocked."
    try:
        doc = json.loads(body)
        if doc.get("name") != "ithute-auth":
            return 1, "Registry returned unexpected package identity."
        latest = doc.get("dist-tags", {}).get("latest", "unknown")
        return 0, f"Public package record exists; latest={latest}. Verify actual publisher ownership separately."
    except (ValueError, TypeError, AttributeError):
        return 1, "Registry returned malformed package metadata."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-published", action="store_true")
    args = parser.parse_args()
    req = urllib.request.Request(REGISTRY, headers={"Accept":"application/json","User-Agent":USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            state, message = classify(response.status, response.read(1_000_000))
    except urllib.error.HTTPError as err:
        state, message = classify(err.code, b"")
    except (urllib.error.URLError, TimeoutError) as err:
        print(f"Registry unreachable ({type(err).__name__}). Release blocked.", file=sys.stderr)
        return 1
    print(message)
    if state == 1 or (args.expect_published and state != 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
