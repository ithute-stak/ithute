#!/usr/bin/env sh
set -eu

: "${BOOTSTRAP_PUBLIC_IP:?BOOTSTRAP_PUBLIC_IP is required}"
RUNTIME_FILE="${CADDY_RUNTIME_FILE:-/platform-runtime/Caddyfile}"
mkdir -p "$(dirname "$RUNTIME_FILE")"

if [ ! -s "$RUNTIME_FILE" ]; then
  umask 022
  cat > "$RUNTIME_FILE" <<EOF
{
    admin 0.0.0.0:2019
}

http://${BOOTSTRAP_PUBLIC_IP} {
    encode zstd gzip
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
    }

    @api path /api/*
    handle @api {
        reverse_proxy backend:8000
    }

    handle {
        reverse_proxy frontend:3000
    }
}
EOF
fi

# Tutor is a first-party Ithute product with its own frontend/backend/database.
# Append its stable host block without replacing the platform runtime config.
if ! grep -q "BEGIN ITHUTE TUTOR" "$RUNTIME_FILE"; then
  cat >> "$RUNTIME_FILE" <<'EOF'

# BEGIN ITHUTE TUTOR
tutor.ithute.co.ls {
    encode zstd gzip
    header {
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
        -Server
    }

    @tutor_api path /api/*
    handle @tutor_api {
        uri strip_prefix /api
        reverse_proxy tutor-backend:8000
    }

    @tutor_media path /media/*
    handle @tutor_media {
        reverse_proxy tutor-backend:8000
    }

    handle {
        reverse_proxy tutor-frontend:3000
    }
}
# END ITHUTE TUTOR
EOF
fi

exec caddy run --config "$RUNTIME_FILE" --adapter caddyfile
