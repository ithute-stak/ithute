#!/usr/bin/env python3
"""Reconcile only Ithute Tutor production settings in the shared .env file."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path


def placeholder(value: str) -> bool:
    text = (value or "").lower()
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

    def ensure_csv(key: str, entry: str, central: bool = False) -> None:
        nonlocal central_changed
        parts = [item.strip() for item in values.get(key, "").split(",") if item.strip()]
        if entry not in parts:
            parts.append(entry)
            updates[key] = ",".join(parts)
            values[key] = updates[key]
            if central:
                central_changed = True

    tutor_secret = values.get("ITHUTE_TUTOR_PUSH_SERVICE_CLIENT_SECRET", "")
    if placeholder(tutor_secret):
        tutor_secret = secrets.token_hex(32)
        updates["ITHUTE_TUTOR_PUSH_SERVICE_CLIENT_SECRET"] = tutor_secret
        values["ITHUTE_TUTOR_PUSH_SERVICE_CLIENT_SECRET"] = tutor_secret

    db_password = values.get("ITHUTE_TUTOR_DB_PASSWORD", "")
    if placeholder(db_password):
        updates["ITHUTE_TUTOR_DB_PASSWORD"] = secrets.token_hex(32)
        values["ITHUTE_TUTOR_DB_PASSWORD"] = updates["ITHUTE_TUTOR_DB_PASSWORD"]

    updates.update(
        {
            "ITHUTE_TUTOR_IMAGE_TAG": deploy_sha,
            "ITHUTE_TUTOR_PUBLIC_URL": "https://tutor.ithute.co.ls",
            "ITHUTE_TUTOR_FRONTEND_URL": "https://tutor.ithute.co.ls",
            "ITHUTE_TUTOR_OIDC_REDIRECT_URI": "https://tutor.ithute.co.ls/api/auth/oidc/callback",
            "ITHUTE_TUTOR_COOKIE_SECURE": "true",
            "ITHUTE_TUTOR_LEGACY_AUTH_ENABLED": "false",
        }
    )

    # Central identity is shared, but this reconciler only adds/updates Tutor's
    # own registration. Existing clients and product registrations are preserved.
    ensure_csv("ITHUTE_AUTH_FIRST_PARTY_CLIENTS", "ithute-tutor:Ithute Tutor", True)
    ensure_csv("ITHUTE_PUSH_ALLOWED_USER_CLIENTS", "ithute-tutor", True)
    ensure_csv("ITHUTE_PUSH_ALLOWED_SERVICE_CLIENTS", "ithute-tutor", True)
    ensure_csv("ITHUTE_AUTH_CORS_ORIGINS", "https://tutor.ithute.co.ls", True)

    try:
        redirects = json.loads(values.get("ITHUTE_AUTH_REDIRECT_URIS_JSON") or "{}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid ITHUTE_AUTH_REDIRECT_URIS_JSON: {exc}") from exc

    callback = "https://tutor.ithute.co.ls/api/auth/oidc/callback"
    current_callbacks = redirects.get("ithute-tutor") or []
    if callback not in current_callbacks:
        redirects["ithute-tutor"] = [*current_callbacks, callback]
        updates["ITHUTE_AUTH_REDIRECT_URIS_JSON"] = json.dumps(
            redirects, separators=(",", ":")
        )
        values["ITHUTE_AUTH_REDIRECT_URIS_JSON"] = updates[
            "ITHUTE_AUTH_REDIRECT_URIS_JSON"
        ]
        central_changed = True

    try:
        service_secrets = json.loads(
            values.get("ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON") or "{}"
        )
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Invalid ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON: {exc}"
        ) from exc

    if service_secrets.get("ithute-tutor") != tutor_secret:
        service_secrets["ithute-tutor"] = tutor_secret
        updates["ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON"] = json.dumps(
            service_secrets, separators=(",", ":")
        )
        values["ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON"] = updates[
            "ITHUTE_AUTH_SERVICE_CLIENT_SECRETS_JSON"
        ]
        central_changed = True

    if updates:
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
