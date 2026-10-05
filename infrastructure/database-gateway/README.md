# Ithute Database Gateway

The database gateway is the stable TCP endpoint for managed PostgreSQL replication groups.

Each PostgreSQL group receives a stable `gateway-hostname:port` pair. The Go router polls the Ithute control plane for authenticated route snapshots and forwards new TCP connections to the current primary.

Required environment:

- `ITHUTE_DB_GATEWAY_API_URL` — API base URL including the API prefix used by the hosting endpoints.
- `ITHUTE_DB_GATEWAY_TOKEN` — one-time `ith_dbgw_...` credential created by the platform owner.
- `ITHUTE_DB_GATEWAY_BIND_IP` — defaults to `0.0.0.0`.
- `ITHUTE_DB_GATEWAY_POLL_SECONDS` — defaults to 5, valid 2..60.
- `ITHUTE_DB_GATEWAY_DIAL_TIMEOUT_SECONDS` — defaults to 5, valid 1..30.

HTTP control-plane access requires HTTPS by default. `ITHUTE_DB_GATEWAY_ALLOW_HTTP=true` exists only for isolated development/test environments.

The configured endpoint port range defaults to 20000..39999 on the control plane. Firewall rules must expose only the assigned endpoint ports to approved application networks.

A route generation is acknowledged only after the local listener is active. PostgreSQL failover RTO is therefore measured to real gateway route application when a stable endpoint exists.
