#!/bin/sh
set -eu

# /auth is a persistent named volume shared with the backend. A brand-new
# production installation has no groupware credentials yet, but Radicale still
# requires its configured htpasswd file to exist before the server can start.
mkdir -p /auth /var/lib/radicale/collections
if [ ! -e /auth/users ]; then
  umask 077
  : > /auth/users
fi

exec "$@"
