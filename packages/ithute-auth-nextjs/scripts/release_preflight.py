#!/usr/bin/env python3
"""Fail-closed, offline checks for public distribution of the Ithute Auth SDK."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "package.json"
SPDX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.()+-]*$")


def check(strict: bool = False) -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    errors = []
    if manifest.get("name") != "ithute-auth":
        errors.append("Package must be named ithute-auth.")
    if manifest.get("private") is True:
        errors.append("Package is still marked private.")
    if manifest.get("main") != "./dist/index.js" or manifest.get("types") != "./dist/index.d.ts":
        errors.append("Expected compiled distribution entry points.")
    if manifest.get("files") != ["dist", "README.md"]:
        errors.append("Package files allowlist must contain only dist and README.md.")
    exports = manifest.get("exports", {}).get(".", {})
    if exports.get("import") != "./dist/index.js" or exports.get("types") != "./dist/index.d.ts":
        errors.append("Package exports must target compiled artifacts.")
    if not (ROOT / "README.md").is_file():
        errors.append("README must exist in publishable package.")
    if strict:
        license_id = manifest.get("license", "")
        if license_id == "UNLICENSED" or not SPDX.fullmatch(license_id):
            errors.append("Approve an explicit SPDX distribution license before release.")
        if not (ROOT / "LICENSE").is_file():
            errors.append("Include an approved LICENSE file before public release.")
        if not (ROOT / "CHANGELOG.md").is_file():
            errors.append("Include a versioned CHANGELOG.md before public release.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Reject packages not approved for a public release")
    args = parser.parse_args()
    errors = check(strict=args.strict)
    if errors:
        for error in errors:
            print("BLOCKED:", error)
        return 1
    print("Local package manifest checks passed.")
    if not args.strict:
        print("This is packaging validation only, not publishing authorization.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
