#!/usr/bin/env python3
"""Adversarial black-box assertions for a disposable Ithute API candidate."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request


def request(base: str, path: str, *, method: str = "GET", headers: dict[str, str] | None = None, body: bytes | None = None):
    req = urllib.request.Request(base.rstrip("/") + path, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def header(headers: dict[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    status, headers, body = request(args.base_url, "/health/live")
    assert status == 200, (status, body[:500])
    assert header(headers, "x-content-type-options").lower() == "nosniff"
    assert header(headers, "x-frame-options").upper() == "DENY"
    assert "default-src 'none'" in header(headers, "content-security-policy")
    assert "camera=()" in header(headers, "permissions-policy")
    assert header(headers, "referrer-policy").lower() == "same-origin"

    status, _, _ = request(args.base_url, "/health/live", method="TRACE")
    assert status >= 400, f"TRACE unexpectedly accepted with HTTP {status}"

    status, _, body = request(
        args.base_url,
        "/api/v1/nonexistent-adversarial-target",
        method="POST",
        headers={"Origin": "https://attacker.invalid", "Content-Type": "application/json"},
        body=b"{}",
    )
    assert status == 403, (status, body[:500])
    parsed = json.loads(body.decode("utf-8"))
    assert "Cross-origin API mutation rejected" in str(parsed.get("detail"))

    status, _, body = request(
        args.base_url,
        "/api/v1/nonexistent-adversarial-target",
        method="POST",
        headers={"Sec-Fetch-Site": "cross-site", "Content-Type": "application/json"},
        body=b"{}",
    )
    assert status == 403, (status, body[:500])
    parsed = json.loads(body.decode("utf-8"))
    assert "Cross-site API mutation rejected" in str(parsed.get("detail"))

    status, headers, _ = request(args.base_url, "/api/v1/%2e%2e/%2e%2e/etc/passwd")
    assert status >= 400
    assert header(headers, "x-content-type-options").lower() == "nosniff"

    print("Adversarial HTTP boundary checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
