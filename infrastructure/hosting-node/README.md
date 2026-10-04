# Ithute Shared Hosting Node

This directory packages the **production runtime host boundary** for Ithute shared hosting. It is separate from the public Ithute control plane and from the isolated build plane.

A hosting node runs customer application containers and, when enabled, dedicated PostgreSQL/MySQL services for hosted customers. It must **not** be a LoanHub, Khanya, Tutor, NBros, Ithute control-plane, or build-plane host.

## Security model

- Customer applications never receive host SSH, the Docker socket, database-admin credentials, or another customer's secrets.
- The production agent entrypoint is `agent_v4.py`.
- Every project receives a dedicated Docker bridge subnet from `ITHUTE_HOSTING_NETWORK_POOL` (default `10.240.0.0/12`, `/28` per project).
- `apply-egress-firewall.sh` protects the entire reserved pool in `DOCKER-USER` **before** customer containers start.
- `ithute-hosting-egress.service` reapplies that policy after Docker starts and before the hosting agent, so the deny-by-default boundary is part of the host boot lifecycle rather than a one-time shell command.
- Private/link-local/metadata destinations and arbitrary outbound ports are denied. DNS, HTTP, HTTPS and the configured local DB gateway are the only default exceptions.
- The firewall script changes only the Ithute custom chain and its one reserved-pool jump. It does not flush the VPS firewall or prune Docker resources.
- `validate-host.sh` fails if database listeners are wildcard/public, if an unrelated Docker network overlaps the reserved pool, if the egress policy is missing, if the persistent egress service is not enabled/active, or if known foreign product containers are present.
- Set `ITHUTE_HOSTING_REQUIRE_AGENT_ACTIVE=true` for the final production-readiness pass to additionally require the hosting agent unit to be installed, enabled and active.

## PostgreSQL ownership model

PostgreSQL should run as a **dedicated Ithute hosting database service**. The hosting agent uses `ithute_hosting_admin`, which needs `CREATEDB` and `CREATEROLE` but must not be SUPERUSER.

Run `postgresql-bootstrap.sql` once as the cluster administrator and provide a protected `hosting_admin_password` psql variable. The v4 agent then:

1. creates a project-scoped customer login role;
2. creates the database as `ithute_hosting_admin`, so the admin can later drop it without SUPERUSER;
3. revokes PostgreSQL's default `PUBLIC` `CONNECT`/`TEMPORARY` access on the database;
4. grants only the customer role `CONNECT` and `TEMPORARY`;
5. revokes `PUBLIC CREATE` on the `public` schema;
6. grants only the customer role `USAGE, CREATE` on that schema;
7. runs PostgreSQL backup/restore with `--role <customer-role>`, preserving customer ownership of application objects.

The agent refuses to delete or restore a PostgreSQL database whose database owner is not the configured Ithute hosting admin. Legacy test databases created with customer database ownership must be migrated deliberately before using v4 production lifecycle operations.

### PostgreSQL listener / HBA requirements

The admin connection should remain loopback/private, for example `127.0.0.1:5432`. Customer containers connect through the fixed `ithute-db-gateway` host alias. PostgreSQL therefore needs a private listener reachable at the Docker host gateway, **not** `0.0.0.0`.

`pg_hba.conf` should allow only the reserved hosted source pool with password authentication, for example conceptually:

```text
hostssl all all 10.240.0.0/12 scram-sha-256
```

Use the actual configured pool and require TLS if the node's PostgreSQL deployment supports it. Do not expose TCP/5432 on a public interface or security group.

## MySQL ownership model

MySQL must also be a **dedicated Ithute hosting database service**. The current agent creates/deletes databases and customer users dynamically and grants each customer user rights over its database. The administrative account therefore has broad lifecycle/grant capability within that MySQL instance.

Do **not** point `ITHUTE_HOSTING_MYSQL_ADMIN_*` at a MySQL instance that contains LoanHub, Khanya, mail, finance, or unrelated application schemas. Keep the MySQL listener on loopback/private interfaces and expose TCP/3306 only to the reserved hosted network pool through the node firewall.

A narrower MySQL privilege broker can be added later, but the safe current production boundary is a dedicated hosted-customer MySQL instance.

## Off-node database backups

Production configuration sets `ITHUTE_HOSTING_BACKUP_REMOTE_REQUIRED=true`. `agent_v4.py` therefore refuses to start unless `ITHUTE_HOSTING_BACKUP_REMOTE` is configured.

The implementation uses `rclone`, so the remote may be S3-compatible object storage, SFTP, another supported cloud store, or another deliberately separated storage system. The actual `rclone.conf` is runtime-only and must never be committed.

A backup is reported **successful** to the control plane only after all of these are true:

1. the engine-native dump completes;
2. the local file has a valid bounded size and SHA-256;
3. the file is atomically promoted into `/var/lib/ithute-hosting/database-backups`;
4. the off-node object is uploaded with immutable-copy semantics;
5. the remote object size matches the local file;
6. a SHA-256 sidecar is written beside the remote object.

Restore never trusts the remote store by itself. If the local file is missing or fails the control-plane size/SHA-256 check, the agent deletes the bad local copy, downloads the remote object to a temporary path, atomically promotes it, and **re-checks the exact control-plane size and SHA-256 before running PostgreSQL/MySQL restore**.

This means a fresh replacement node can restore a database whose local backup volume was lost, provided the same control-plane records and off-node object store are available.

Use the remote storage provider's lifecycle/versioning policy for long-term retention. Ithute's application-level backup record remains the source of truth for the expected checksum and size; storage-provider retention is an additional durability layer, not a replacement for application integrity checks.

## Installation layout

Recommended host paths:

```text
/etc/ithute-hosting-node/agent.env                 # mode 0600
/etc/ithute-hosting-node/rclone.conf               # mode 0600
/opt/ithute-hosting-node/apply-egress-firewall.sh
/opt/ithute-hosting-agent/agent.py
/opt/ithute-hosting-agent/agent_v3.py
/opt/ithute-hosting-agent/agent_v4.py
/opt/ithute-hosting-agent/network_policy.py
/opt/ithute-hosting-agent/backup_remote.py
/var/lib/ithute-hosting/database-backups/
/etc/systemd/system/ithute-hosting-egress.service
/etc/systemd/system/ithute-hosting-agent.service
```

Create a dedicated `ithute-hosting-agent` system user, add only that account to the Docker group, and copy `agent.env.example` to the protected environment file. The provided systemd agent unit runs v4 with a read-only host filesystem except for `/var/lib/ithute-hosting`.

Install `apply-egress-firewall.sh` at `/opt/ithute-hosting-node/apply-egress-firewall.sh` with root ownership and executable permissions. Install `ithute-hosting-egress.service`, run `systemctl daemon-reload`, and enable/start that unit before the hosting agent. The egress unit is ordered after Docker and before `ithute-hosting-agent.service`.

Required host utilities depend on enabled engines:

- Docker Engine / CLI;
- Python 3.12+;
- `iptables`, `ss` and `systemctl`;
- `rclone` for required off-node backup replication;
- PostgreSQL client tools: `psql`, `createdb`, `dropdb`, `pg_dump`, `pg_restore`;
- MySQL client tools: `mysql`, `mysqldump`.

## Bring-up order

1. Prepare a **dedicated hosting node**.
2. Reserve a private Docker CIDR that does not overlap any existing host/VPC/Docker network.
3. Configure private PostgreSQL/MySQL listeners and authentication.
4. Bootstrap the PostgreSQL admin role if PostgreSQL is enabled.
5. Configure a separate off-node `rclone` destination and protect `rclone.conf` with mode `0600`.
6. Install `agent_v4.py`, `backup_remote.py`, its base modules, environment file, both systemd units, and the egress firewall script.
7. Run `systemctl daemon-reload`, then `systemctl enable --now ithute-hosting-egress.service`. Do not start customer workloads if this unit fails.
8. Run `validate-host.sh`; do not proceed unless it passes. This proves the current firewall state and its boot persistence unit are present.
9. Register/rotate the one-time node token in Ithute and store it only in `agent.env`.
10. Run `systemctl enable --now ithute-hosting-agent.service`. With the production template it will fail fast if the required backup remote is absent.
11. Run `ITHUTE_HOSTING_REQUIRE_AGENT_ACTIVE=true validate-host.sh`; this is the strict service-lifecycle readiness pass.
12. Deploy a disposable test project and database, verify outbound web access, verify RFC1918/metadata/SMTP blocking, test DB provision/rotate/suspend/resume/delete, then test backup + suspended restore.
13. Delete the disposable node-local backup and repeat restore to prove remote rehydration works before accepting customer workloads.
14. Reboot the host and repeat the strict validator. Then restart Docker and repeat it again before accepting customer workloads.

## What is still a production validation task

These files make node setup reproducible and fail-closed, but they do not claim a VPS has already been validated. Before PR #219 is merged, a real dedicated hosting node still needs an end-to-end deployment exercise covering:

- actual reboot and Docker-restart verification that `ithute-hosting-egress.service` restores the required policy before the hosting agent resumes workloads;
- actual Docker/VPC CIDR non-overlap;
- PostgreSQL/MySQL private listeners and authentication;
- registry/image transfer into the runtime node;
- Caddy/public ingress from verified domains to healthy private containers;
- off-node backup credentials, lifecycle/versioning policy and an actual node-loss/remote-rehydration restore drill;
- resource pressure and abuse tests.


## Private origin handoff to Ithute Edge

Hosted containers still do **not** receive arbitrary public host ports. When
automatic edge provisioning is enabled, the hosting node may expose a narrowly
controlled HTTP origin on a dedicated **private/VPN IPv4 address**.

Configure:

- `ITHUTE_HOSTING_ORIGIN_BIND_IP` to a private/VPN address assigned to the hosting node;
- `ITHUTE_HOSTING_ORIGIN_PORT_START` / `ITHUTE_HOSTING_ORIGIN_PORT_END` to the reserved range;
- `ITHUTE_EDGE_ORIGIN_CIDRS` to the exact private/VPN CIDRs of the Ithute edge hosts;
- the control plane's `ITHUTE_HOSTING_ORIGIN_CIDRS` to the trusted hosting-origin network.

The node agent deterministically allocates a port inside the reserved range,
binds only to the configured private address, health-checks the container on its
isolated Docker network, and reports the origin to the control plane only after
the deployment is healthy.

`apply-egress-firewall.sh` also creates `ITHUTE-HOSTING-INGRESS`. Docker
published-origin traffic is matched using the connection's original destination
and is accepted only from the configured edge CIDRs; every other source is
rejected.

The control plane refuses public, hostname-based, loopback, link-local, wildcard
or out-of-CIDR origin reports. Edge routing is not marked complete until DNS
points to Ithute Edge, the trusted origin is reachable, Caddy accepts the route,
and public HTTPS responds successfully.
