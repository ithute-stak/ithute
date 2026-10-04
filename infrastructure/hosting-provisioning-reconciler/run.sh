#!/usr/bin/env bash
set -euo pipefail

ITHUTE_DIR="${ITHUTE_DIR:-/opt/ithute}"
cd "$ITHUTE_DIR"

docker compose -f compose.production.yml exec -T ithute-app-api \
  python -m app.services.hosting_provisioning_reconcile_cli
