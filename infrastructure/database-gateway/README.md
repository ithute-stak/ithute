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


## High availability pools

For production, configure at least two independently hosted gateway instances and register them in one database gateway pool. The pool exposes one shared frontend hostname and one stable port per PostgreSQL replication group.

The shared frontend hostname must resolve or route to every active gateway member (for example, multiple DNS A/AAAA records, an anycast address, or an external L4 load balancer). Ithute does not mark a generation ready until the configured number of independent gateway members have:

1. received the current route generation;
2. installed the local TCP listener;
3. successfully probed the current PostgreSQL primary; and
4. acknowledged that exact generation.

The default production recommendation is two gateways with `required_ready_gateways=2`. This favors correctness and verified reachability over silent degradation. A lower quorum is available only as an explicit policy choice.

Gateway heartbeats are continuously reconciled. If fresh gateway membership drops below quorum, the pool and its PostgreSQL endpoints become `degraded` even after an earlier successful cutover.
