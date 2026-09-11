# Central Nginx Docker DNS invariant

The Mailbox DNS Nginx gateway is long-lived while central Ithute Auth, Push and Realtime containers may be recreated during independent product releases. Their Docker IP addresses therefore must never be captured by a static `proxy_pass http://service:port` at Nginx configuration load time.

`infrastructure/nginx/default.conf` uses Docker's embedded resolver (`127.0.0.11`) and variable-based upstreams for `ithute-auth`, `ithute-push` and `ithute-realtime`. This forces request-time DNS resolution and prevents a container recreation from producing persistent public 502 responses through the shared Ithute TLS edge.

The `Central Nginx Routing Contract` workflow rejects a release if those central routes regress to static proxy addresses.
