#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARKER = "# Nthane Brothers Construction Management System."

NBROS_BLOCK = r'''# Nthane Brothers NBros management platform. NBros owns its PostgreSQL,
# Redis and uploads while the shared Ithute edge owns public TLS/routing.
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name nbro.ithute.co.ls;

    ssl_certificate /etc/letsencrypt/live/ithute-edge/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ithute-edge/privkey.pem;
    include /etc/nginx/snippets/ithute-tls.conf;

    client_max_body_size 25m;
    set $nbros_backend http://nbros-backend:8000;
    set $nbros_frontend http://nbros-frontend:3000;

    location ^~ /api/v1/ {
        proxy_pass $nbros_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 10s;
        proxy_read_timeout 300s;
    }

    location ^~ /api/fleet/ {
        proxy_pass $nbros_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 10s;
        proxy_read_timeout 300s;
    }

    location = /healthz {
        proxy_pass $nbros_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }

    location = /readyz {
        proxy_pass $nbros_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }

    location / {
        proxy_pass $nbros_frontend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_connect_timeout 10s;
        proxy_read_timeout 120s;
    }
}'''


def replace_server_block(source: str) -> str:
    marker_at = source.find(MARKER)
    if marker_at < 0:
        raise SystemExit("Nthane Brothers edge marker not found")
    server_at = source.find("server {", marker_at)
    if server_at < 0:
        raise SystemExit("Nthane Brothers server block not found")

    depth = 0
    end = None
    for index in range(server_at, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise SystemExit("Nthane Brothers server block is unbalanced")

    prefix = source[:marker_at].rstrip()
    suffix = source[end:].lstrip("\n")
    rendered = f"{prefix}\n\n{NBROS_BLOCK}\n\n{suffix}"
    if rendered.count("server_name nbro.ithute.co.ls;") != 1:
        raise SystemExit("Rendered edge must contain exactly one NBros virtual host")
    if "buildtrack-backend" in rendered or "buildtrack-frontend" in rendered:
        raise SystemExit("Legacy BuildTrack edge aliases remain after rendering")
    return rendered


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: render-shared-edge.py SOURCE DESTINATION")
    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    destination = Path(sys.argv[2])
    destination.write_text(replace_server_block(source), encoding="utf-8")


if __name__ == "__main__":
    main()
