#!/bin/sh
set -eu

ROUTING_DIR="${ITHUTE_MAIL_ROUTING_DIR:-/routing}"

test -f "$ROUTING_DIR/.ready" || {
  echo "Ithute routing maps are not reconciled yet: missing $ROUTING_DIR/.ready" >&2
  exit 2
}

for file in relay-domains.cf relay-recipients.cf transport.cf virtual-aliases.cf; do
  test -f "$ROUTING_DIR/$file" || {
    echo "Missing required routing map: $ROUTING_DIR/$file" >&2
    exit 2
  }
done

postfix check
exec postfix start-fg
