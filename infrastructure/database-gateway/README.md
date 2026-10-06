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

For production pools created through the platform API, the shared frontend hostname must live below a verified Ithute-managed DNS domain. Each gateway registers at least one routable IPv4/IPv6 address. The hosting health daemon reconciles PowerDNS with the fresh pool members using TTL 60 records, automatically withdrawing stale gateway addresses and restoring them when health returns. An external anycast or L4 load balancer can still be used as an optional frontend architecture, but it is not required for the standard PowerDNS-backed HA path.

Ithute does not mark a generation ready until the configured number of independent gateway members have:

1. received the current route generation;
2. installed the local TCP listener;
3. successfully probed the current PostgreSQL primary; and
4. acknowledged that exact generation.

The default production recommendation is two gateways with `required_ready_gateways=2`. This favors correctness and verified reachability over silent degradation. A lower quorum is available only as an explicit policy choice.

Gateway heartbeats are continuously reconciled. If fresh gateway membership drops below quorum, the pool and its PostgreSQL endpoints become `degraded` even after an earlier successful cutover.


### DNS failover safety

PowerDNS publication state is persisted on the gateway pool. The health loop only writes DNS when the desired healthy address set changes, avoiding serial/record churn on every poll. The last reconciliation timestamp and DNS error are retained. A PowerDNS reconciliation failure degrades the pool instead of reporting healthy HA.

The normal production sequence is:

1. register at least two database gateways with distinct routable addresses;
2. create a gateway pool bound to a verified Ithute-managed DNS domain;
3. attach the PostgreSQL replication group endpoint to that pool;
4. wait for every required router to install/probe/ACK the route generation;
5. expose the pool frontend hostname and stable endpoint port to applications.
