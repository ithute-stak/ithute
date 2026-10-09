#!/usr/bin/env python3
"""Safe, read-only public smoke checks for the Ithute developer portal.

Usage: python3 scripts/check-developer-portal.py https://ithute.co.ls
No credentials or secrets are sent. Checks must fail closed on network errors.
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

def check(base: str, path: str, allowed: set[int], *, method: str = "GET") -> tuple[bool, str]:
    url = base + path
    request = urllib.request.Request(url, method=method, headers={"User-Agent": "Ithute-Developer-Smoke/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            status = response.status
            body = response.read(65536)
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read(65536)
        content_type = error.headers.get("Content-Type", "")
    except (urllib.error.URLError, TimeoutError) as error:
        return False, f"{path}: connection failed ({type(error).__name__})"

    valid = status in allowed
    if method == "GET" and valid and status == 200:
        valid = "text/html" in content_type and b"<html" in body.lower()
    return valid, f"{path}: HTTP {status} ({'PASS' if valid else 'FAIL'})"

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", help="Trusted HTTPS origin, e.g. https://ithute.co.ls")
    args = parser.parse_args()
    origin = urllib.parse.urlsplit(args.origin)
    if origin.scheme != "https" or not origin.hostname or origin.username or origin.password or origin.path not in ("", "/") or origin.query or origin.fragment:
        parser.error("Origin must be a bare HTTPS host URL")
    base = f"https://{origin.netloc}"
    checks = [
        ("/developer", {200}, "GET"),
        ("/developer/docs", {200}, "GET"),
        ("/developer/auth", {200}, "GET"),
        ("/developer/register", {200}, "GET"),
        ("/developer/dashboard", {200}, "GET"),
        # No Origin or credentials: registration and developer actions must reject.
        ("/developer/api/register", {403, 405}, "POST"),
        ("/api/v1/auth/ithute/developer/requests", {401, 403, 503}, "GET"),
    ]
    failures = 0
    for path, statuses, method in checks:
        ok, message = check(base, path, statuses, method=method)
        print(message)
        failures += not ok
    print(json.dumps({"origin": base, "checks": len(checks), "failed": failures}))
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
