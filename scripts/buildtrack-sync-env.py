#!/usr/bin/env python3
"""Reconcile Nthane Brothers BuildTrack settings in the shared production .env.

The script is intentionally additive: sibling product registrations and secrets
are preserved. No human password is generated or stored here.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

CLIENT_ID = "buildtrack-construction"
PRODUCT_NAME = "Nthane Brothers Construction"
PUBLIC_URL = "https://nbro.ithute.co.ls"
CALLBACK = f"{PUBLIC_URL}/api/v1/access/oidc/callback"
SUPERADMIN_EMAIL = "justy@ithute.co.ls"
PRODUCT_ADMIN_EMAILS = "justy@ithute.co.ls,just@ithute.co.ls"


def placeholder(value: str) -> bool:
    text = (value or "").strip().lower()
    return (
        not text
        or "replace-with" in text
        or "replace-this" in text
        or "changeme" in text
    )


def main() -> None:
    deploy_sha = os.environ.get("DEPLOY_SHA", "").strip()
    if not deploy_sha:
        raise SystemExit("DEPLOY_SHA is required")

    path = Path(os.environ.get("ITHUTE_ENV_FILE", ".env"))
    if not path.is_file():
        raise SystemExit(f"Production env file is missing: {path}")

    original = path.read_text().splitlines()
    values: dict[str, str] = {}
    for line in original:
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value

    updates: dict[str, str] = {}
    central_changed = False

    def ensure_csv(key: str, entry: str, *, central: bool = False) -> None:
        nonlocal central_changed
        items = [item.strip() for item in values.get(key, "").split(",") if item.strip()]
        if entry not in items:
            items.append(entry)
            values[key] = updates[key] = ",".join(items)
            central_changed = central_changed or central

    db_password = values.get("ITHUTE_BUILDTRACK_DB_PASSWORD", "")
    if placeholder(db_password):
        values["ITHUTE_BUILDTRACK_DB_PASSWORD"] = updates["ITHUTE_BUILDTRACK_DB_PASSWORD"] = secrets.token_hex(32)

    service_secret = values.get("ITHUTE_BUILDTRACK_PUSH_SERVICE_CLIENT_SECRET", "")
    if placeholder(service_secret):
        service_secret = secrets.token_hex(32)
        values["ITHUTE_BUILDTRACK_PUSH_SERVICE_CLIENT_SECRET"] = updates["ITHUTE_BUILDTRACK_PUSH_SERVICE_CLIENT_SECRET"] = service_secret

    updates.update(
        {
            "ITHUTE_BUILDTRACK_IMAGE_TAG": deploy_sha,
            "ITHUTE_BUILDTRACK_PUBLIC_URL": PUBLIC_URL,
            "ITHUTE_BUILDTRACK_OIDC_REDIRECT_URI": CALLBACK,
            "ITHUTE_BUILDTRACK_SUPERADMIN_EMAIL": SUPERADMIN_EMAIL,
            "ITHUTE_BUILDTRACK_PRODUCT_ADMIN_EMAILS": PRODUCT_ADMIN_EMAILS,
        }
    )
    values.update(updates)

    ensure_csv("ITHUTE_AUTH_FIRST_PARTY_CLIENTS", f"{CLIENT_ID}:{PRODUCT_NAME}", central=True)
    ensure_csv("ITHUTE_AUTH_CORS_ORIGINS", PUBLIC_URL, central=True)
    ensure_csv("ITHUTE_PUSH_ALLOWED_USER_CLIENTS", CLIENT_ID, central=True)
    ensure_csv("ITHUTE_PUSH_ALLOWED_SERVICE_CLIENTS", CLIENT_ID, central=True)
    ensure_csv("ITHUTE_REALTIME_ALLOWED_USER_CLIENTS", CLIENT_ID, central=True)
    ensure_csv("ITHUTE_REALTIME_ALLOWED_SERVICE_CLIENTS", CLIENT_ID, central=True)

    try:
        redirects = json.loads(values.get("ITHUTE_AUTH_REDIRECT_URIS_JSON") or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid ITHUTE_AUTH_REDIRECT_URIS_JSON: {exc}") from exc
    if not isinstance(redirects, dict):
        raise SystemExit("ITHUTE_AUTH_REDIRECT_URIS_JSON must be a JSON object")
    callbacks = redirects.get(CLIENT_ID) or []
    if not isinstance(callbacks, list):
        raise SystemExit(f"{CLIENT_ID} redirect configuration must be an array")
    if CALLBACK not in callbacks:
        redirects[CLIENT_ID] = [*callbacks, CALLBACK]
        values["ITHUTE_AUTH_REDIRECT_URIS_JSON"] = updates["ITHUTE_AUTH_REDIRECT_URIS_JSON"] = json.dumps(redirects, separators=(",", ":"))
        central_changed = True

    try:
        service_secrets = json.loads(values.get("ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON") or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON: {exc}") from exc
    if not isinstance(service_secrets, dict):
        raise SystemExit("ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON must be a JSON object")
    if service_secrets.get(CLIENT_ID) != service_secret:
        service_secrets[CLIENT_ID] = service_secret
        values["ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON"] = updates["ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON"] = json.dumps(service_secrets, separators=(",", ":"))
        central_changed = True

    seen: set[str] = set()
    rendered: list[str] = []
    for line in original:
        if line and not line.lstrip().startswith("#") and "=" in line:
            key = line.split("=", 1)[0]
            if key in updates:
                rendered.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        rendered.append(line)
    for key, value in updates.items():
        if key not in seen:
            rendered.append(f"{key}={value}")
    path.write_text("\n".join(rendered) + "\n")

    print("true" if central_changed else "false")


if __name__ == "__main__":
    main()
