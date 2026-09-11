#!/usr/bin/env sh
set -eu

: "${RUNTIME_DIR:?RUNTIME_DIR is required}"
: "${PRODUCT_HOST:?PRODUCT_HOST is required}"

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

python3 - "$RUNTIME_DIR/.env" "$PRODUCT_HOST" <<'PY'
from pathlib import Path
import re
import secrets
import shlex
import sys

path = Path(sys.argv[1])
host = sys.argv[2]
values: dict[str, str] = {}
order: list[str] = []

if path.exists():
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in values:
            order.append(key)
        values[key] = value


def secret_value(key: str) -> str:
    value = values.get(key, "")
    if len(value) >= 24 and "\n" not in value and "\r" not in value:
        return value
    return secrets.token_hex(32)

required = {
    "COMPOSE_PROJECT_NAME": "nbros",
    "NBROS_DB_NAME": values.get("NBROS_DB_NAME", "nbros") or "nbros",
    "NBROS_DB_USER": values.get("NBROS_DB_USER", "nbros") or "nbros",
    "NBROS_DB_PASSWORD": secret_value("NBROS_DB_PASSWORD"),
    "NBROS_PUBLIC_URL": f"https://{host}",
    "NBROS_BACKEND_PORT": values.get("NBROS_BACKEND_PORT", "8203") or "8203",
    "NBROS_FRONTEND_PORT": values.get("NBROS_FRONTEND_PORT", "3203") or "3203",
    "NBROS_AUTH_ISSUER": "https://auth.ithute.co.ls",
    "NBROS_AUTH_AUDIENCE": "nbros",
    "NBROS_AUTH_JWKS_URL": "https://auth.ithute.co.ls/.well-known/jwks.json",
    "NBROS_AUTH_SERVICE_TOKEN_URL": "https://auth.ithute.co.ls/v1/auth/service-token",
    "NBROS_BOOTSTRAP_ADMIN_EMAIL": values.get("NBROS_BOOTSTRAP_ADMIN_EMAIL", "justy@ithute.co.ls") or "justy@ithute.co.ls",
    "NBROS_REALTIME_PUBLIC_URL": "https://realtime.ithute.co.ls",
    "NBROS_REALTIME_WS_URL": "wss://realtime.ithute.co.ls/v1/ws",
    "NBROS_REALTIME_SERVICE_CLIENT_SECRET": secret_value("NBROS_REALTIME_SERVICE_CLIENT_SECRET"),
    "NBROS_REALTIME_PUBLISH_ENABLED": "true",
    "NBROS_COOKIE_SECURE": "true",
    "NBROS_AI_ENABLED": values.get("NBROS_AI_ENABLED", "false") or "false",
    "ITHUTE_MAILBOX_NETWORK_NAME": "mailbox-dns_mailbox_dns",
}

for key, value in required.items():
    if key not in values:
        order.append(key)
    values[key] = value

# Keep only valid NBros/runtime keys. This intentionally drops stray prose or
# malformed legacy lines that cannot safely be sourced by POSIX sh.
allowed = [
    key for key in order
    if key.startswith("NBROS_") or key in {"COMPOSE_PROJECT_NAME", "ITHUTE_MAILBOX_NETWORK_NAME"}
]
for key in required:
    if key not in allowed:
        allowed.append(key)

path.write_text(
    "\n".join(f"{key}={shlex.quote(str(values[key]))}" for key in allowed if key in values) + "\n",
    encoding="utf-8",
)
PY

chmod 600 "$RUNTIME_DIR/.env"
echo "NBros production runtime environment normalized."
