#!/usr/bin/env python3
"""Idempotently provision the central Ithute identity for BuildTrack.

The real human credential never belongs to BuildTrack. If the requested central
identity does not exist, this script creates it with an unreachable random
bootstrap credential and asks Ithute Auth to deliver its secure password-setup
link. Existing identities are left unchanged.
"""

from __future__ import annotations

import os
import secrets

import httpx

from app.core.config import get_settings

DEFAULT_ADMIN_EMAIL = "just@ithute.co.ls"


def main() -> None:
    settings = get_settings()
    email = os.environ.get("BUILDTRACK_CENTRAL_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL).strip().lower()
    if not email or "@" not in email:
        raise SystemExit("BUILDTRACK_CENTRAL_ADMIN_EMAIL must be a valid email address")
    if email not in settings.product_admin_email_list:
        raise SystemExit("Central administrator must also be configured as a BuildTrack product administrator")

    base = settings.auth_internal_base_url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            registration = client.post(
                f"{base}/v1/users/register",
                json={
                    "email": email,
                    "display_name": "Nthane Brothers Administrator",
                    "password": secrets.token_urlsafe(48),
                },
            )
            if registration.status_code == 201:
                reset = client.post(
                    f"{base}/v1/account/password/reset/request",
                    json={"identifier": email},
                )
                if reset.status_code != 202:
                    raise SystemExit(
                        f"Central Ithute Auth password setup request failed ({reset.status_code})"
                    )
                print(
                    f"Central Ithute Auth account created for {email}; "
                    "secure password setup instructions requested."
                )
                return
            if registration.status_code == 409:
                print(
                    f"Central Ithute Auth account already exists for {email}; "
                    "no credential was changed."
                )
                return
            raise SystemExit(f"Central Ithute Auth registration failed ({registration.status_code})")
    except httpx.RequestError as exc:
        raise SystemExit("Central Ithute Auth is unavailable during administrator provisioning") from exc


if __name__ == "__main__":
    main()
